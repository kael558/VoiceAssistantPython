#
# Copyright (c) 2024, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import os
import sys

import aiohttp
from dotenv import load_dotenv
from loguru import logger
from openai.types.chat import ChatCompletionToolParam
from pipecat.frames.frames import TextFrame, LLMMessagesFrame, EndFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.processors.aggregators.llm_response import (
    LLMAssistantContextAggregator,
    LLMUserContextAggregator,
)
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.azure import AzureTTSService
from pipecat.services.deepgram import DeepgramSTTService
from pipecat.services.openai import OpenAILLMContext, OpenAILLMService
from pipecat.transports.network.fastapi_websocket import FastAPIWebsocketTransport, FastAPIWebsocketParams
from pipecat.vad.silero import SileroVADAnalyzer

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")


async def start_fetch_weather(llm):
    await llm.push_frame(TextFrame("Let me think."))


async def fetch_weather_from_api(llm, args):
    return {"conditions": "nice", "temperature": "75"}


async def run_bot(websocket_client, stream_sid):

    async with aiohttp.ClientSession() as session:
        transport = FastAPIWebsocketTransport(
            websocket=websocket_client,
            params=FastAPIWebsocketParams(
                audio_out_enabled=True,
                add_wav_header=False,
                vad_enabled=True,
                vad_analyzer=SileroVADAnalyzer(),
                vad_audio_passthrough=True,
                serializer=TwilioFrameSerializer(stream_sid)
            )
        )

        tts = AzureTTSService(
                  api_key=os.getenv("AZURE_SPEECH_API_KEY"),
                  region=os.getenv("AZURE_SPEECH_REGION"),
              )
        stt = DeepgramSTTService(api_key=os.getenv('DEEPGRAM_API_KEY'))

        """tts = ElevenLabsTTSService(
                    aiohttp_session=session,
                    api_key=os.getenv("ELEVENLABS_API_KEY"),
                    voice_id=os.getenv("ELEVENLABS_VOICE_ID"),
                )
        """
        llm = OpenAILLMService(
            api_key=os.getenv("GROQ_API_KEY"),
            model="llama3-groq-8b-8192-tool-use-preview",
            base_url="https://api.groq.com/openai/v1"
        )
        llm.register_function(
            "get_current_weather",
            fetch_weather_from_api,
            start_callback=start_fetch_weather)



        tools = [
            ChatCompletionToolParam(
                type="function",
                function={
                    "name": "get_current_weather",
                    "description": "Get the current weather",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "The city and state, e.g. San Francisco, CA",
                            },
                            "format": {
                                "type": "string",
                                "enum": [
                                    "celsius",
                                    "fahrenheit"],
                                "description": "The temperature unit to use. Infer this from the users location.",
                            },
                        },
                        "required": [
                            "location",
                            "format"],
                    },
                })]
        messages = [
            {
                "role": "system",
                "content": "You are a helpful LLM in a WebRTC call. Your goal is to demonstrate your capabilities in a succinct way. Your output will be converted to audio so don't include special characters in your answers. Respond to what the user said in a creative and helpful way.",
            },
        ]

        context = OpenAILLMContext(messages, tools)
        tma_in = LLMUserContextAggregator(context)
        tma_out = LLMAssistantContextAggregator(context)
        pipeline = Pipeline([
            transport.input(),
            stt,
            tma_in,
            llm,
            tts,
            transport.output(),
            tma_out
        ])

        task = PipelineTask(pipeline, params=PipelineParams(allow_interruptions=True))

        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            logger.info("Client connected.")
            # Kick off the conversation.
            messages.append(
                {"role": "system", "content": "Please introduce yourself to the user."})
            await task.queue_frames([LLMMessagesFrame(messages)])

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport, client):
            await task.queue_frames([EndFrame()])

        runner = PipelineRunner(handle_sigint=False)

        await runner.run(task)
