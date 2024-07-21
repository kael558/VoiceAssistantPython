from dataclasses import dataclass

from groq.types import shared_params
from pipecat.services.ai_services import LLMService
from groq import Groq
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionToolParam,
    ChatCompletionToolChoiceOptionParam
)
from openai._types import NOT_GIVEN, NotGiven

@dataclass
class Param:
    name: str
    type: str
    description: str
    required: bool = True
    enum: list = None


@dataclass
class Tool:
    name: str
    description: str
    params: list[Param]

    actions: list[shared_params.FunctionDefinition]
    active: bool = False



class GroqContext:
    def __init__(
            self,
            messages: list[ChatCompletionMessageParam] = None,
            tools: list[ChatCompletionToolParam] | NotGiven = NOT_GIVEN,
            tool_choice: ChatCompletionToolChoiceOptionParam | NotGiven = NOT_GIVEN
    ):
        self.messages: List[ChatCompletionMessageParam] = messages if messages else [
        ]
        self.tool_choice: ChatCompletionToolChoiceOptionParam | NotGiven = tool_choice
        self.tools: List[ChatCompletionToolParam] | NotGiven = tools

    @staticmethod
    def from_messages(messages: List[dict]) -> "OpenAILLMContext":
        context = OpenAILLMContext()
        for message in messages:
            context.add_message({
                "content": message["content"],
                "role": message["role"],
                "name": message["name"] if "name" in message else message["role"]
            })
        return context

    @staticmethod
    def from_image_frame(frame: VisionImageRawFrame) -> "OpenAILLMContext":
        """
        For images, we are deviating from the OpenAI messages shape. OpenAI
        expects images to be base64 encoded, but other vision models may not.
        So we'll store the image as bytes and do the base64 encoding as needed
        in the LLM service.
        """
        context = OpenAILLMContext()
        buffer = io.BytesIO()
        Image.frombytes(
            frame.format,
            frame.size,
            frame.image
        ).save(
            buffer,
            format="JPEG")
        context.add_message({
            "content": frame.text,
            "role": "user",
            "data": buffer,
            "mime_type": "image/jpeg"
        })
        return context

    def add_message(self, message: ChatCompletionMessageParam):
        self.messages.append(message)

    def get_messages(self) -> List[ChatCompletionMessageParam]:
        return self.messages

    def get_messages_json(self) -> str:
        return json.dumps(self.messages, cls=CustomEncoder)

    def set_tool_choice(
            self, tool_choice: ChatCompletionToolChoiceOptionParam | NotGiven
    ):
        self.tool_choice = tool_choice

    def set_tools(self, tools: List[ChatCompletionToolParam] | NotGiven = NOT_GIVEN):
        if tools != NOT_GIVEN and len(tools) == 0:
            tools = NOT_GIVEN

        self.tools = tools


class CustomLLMService(LLMService):
    def __init__(self, *, model: str, api_key=None, **kwargs):
        super().__init__(**kwargs)
        self._model: str = model
        self._client = Groq(
            api_key=api_key,
        )

    def can_generate_metrics(self) -> bool:
        return True


    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        context = None
        if isinstance(frame, OpenAILLMContextFrame):
            context: OpenAILLMContext = frame.context
        elif isinstance(frame, LLMMessagesFrame):
            context = OpenAILLMContext.from_messages(frame.messages)
        elif isinstance(frame, VisionImageRawFrame):
            context = OpenAILLMContext.from_image_frame(frame)
        else:
            await self.push_frame(frame, direction)

        if context:
            await self.push_frame(LLMFullResponseStartFrame())
            await self.start_processing_metrics()
            await self._process_context(context)
            await self.stop_processing_metrics()
            await self.push_frame(LLMFullResponseEndFrame())
