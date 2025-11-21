#
# Copyright (c) 2024, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#
import json
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
from pipecat.services.elevenlabs import ElevenLabsTTSService
#from pipecat.services.azure import AzureTTSService
from pipecat.services.deepgram import DeepgramSTTService
from pipecat.services.openai import OpenAILLMContext, OpenAILLMService
from pipecat.transports.network.fastapi_websocket import FastAPIWebsocketTransport, FastAPIWebsocketParams
from pipecat.vad.silero import SileroVADAnalyzer
from twilio.rest import Client

from tools.web_search import search_bing
from tools.wifi_controller import toggle_wifi
from tools.bus_router import get_bus_route

from groq import Groq

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")

client = Groq(
    # This is the default and can be omitted
    api_key=os.environ.get("GROQ_API_KEY"),
)

account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
twilio_client = Client(account_sid, auth_token)

def get_tools():
    return [
        {
            "type": "function",
            "function": {
                "name": "search_bing",
                "description": "Search the web. Use this to search up real-time information, current events or weather updates (basically anything that requires latest information).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query",
                        },
                    },
                    "required": ["query"],
                },
            }
        },
        {
            "type": "function",
            "function": {
                "name": "toggle_wifi",
                "description": "Toggle the WiFi",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_bus_route",
                "description": "Find the best public transit route (bus/train/metro) between two locations. Uses Google Maps and optional real-time vehicle positions to recommend the fastest route and when to leave.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "origin": {
                            "type": "string",
                            "description": "Starting location (address or 'lat,lng')."
                        },
                        "destination": {
                            "type": "string",
                            "description": "Destination location (address or 'lat,lng')."
                        },
                        "gtfs_feed_url": {
                            "type": "string",
                            "description": "Optional GTFS Realtime vehicle-positions feed URL. If omitted, only Google Maps schedule data is used."
                        }
                    },
                    "required": ["origin", "destination"],
                },
            }
        },
    ]

async def handle_tools(messages, tool_calls, from_, to_):
    try:
        available_functions = {
            "search_bing": search_bing,
            "toggle_wifi": toggle_wifi,
            "get_bus_route": get_bus_route,
        }

        for tool_call in tool_calls:
            function_name = tool_call.function.name
            function_to_call = available_functions.get(function_name, None)
            if function_to_call:
                function_args = json.loads(tool_call.function.arguments)
                function_response = function_to_call(**function_args)
                messages.append({"role": "tool", "content": function_response, "tool_call_id": tool_call.id, "name": function_name})

        messages.append({"role": "system", "content": "Summarize the tool results in a concise and informative way. Don't use markdown formatting because it will be sent as a text message."})

        second_response = client.chat.completions.create(
            messages=messages,
            model="llama-3.3-70b-versatile"
        )
        twilio_client.messages.create(
            body=second_response.choices[0].message.content,
            from_=to_,
            to=from_
        )
    except Exception as e:
        logger.error(f"Error: {e}")
        twilio_client.messages.create(
            body=f"An error occurred {e}",
            from_=to_,
            to=from_
        )



def choose_tools(message):
    messages = [
        {
            "role": "system",
            "content": "You are an assistant responding to an SMS message. When you need to search for information or use a tool, call the appropriate function. Do not wrap function calls in any tags or special formatting.",
        },
        {
            "role": "user",
            "content": message
        }
    ]
    
    
    tool_choice = "auto"
    
    if message.lower().strip() == 'wifi':
        tool_choice = {"type": "function", "function": {"name": "toggle_wifi"}}

    tools = get_tools()
    response = client.chat.completions.create(
        messages=messages,
        model="openai/gpt-oss-120b",
        tools=tools,
        tool_choice=tool_choice,
 
    )

    response_message = response.choices[0].message
    tool_calls = response_message.tool_calls

    if tool_calls:
        messages.append(response_message)
        return messages, tool_calls

    return response_message.content, None



async def start_search(llm):
    await llm.push_frame(TextFrame("Let me search for that. Give me one second."))


async def search(llm, args):
    try:
        return search_bing(args["query"])
    except Exception as e:
        logger.error(f"Error: {e}")
        return "Failed to retrieve search results"


def simplify_for_voice(text: str) -> str:
    """
    Simplify rich-text route output for voice reading.
    Removes emojis and heavy formatting so TTS sounds natural.
    """
    emojis_to_remove = ["🚌", "📍", "⏱️", "📊", "✅", "🔴", "⬜", "🗺️"]
    for emoji in emojis_to_remove:
        text = text.replace(emoji, "")

    # Remove heavy separators and repeated punctuation
    for ch in ["=", "-", "_"]:
        text = text.replace(ch * 2, " ")

    # Make symbols more voice-friendly
    text = text.replace("~", " approximately ")

    # Collapse excessive whitespace
    return " ".join(text.split())


async def start_bus_routing(llm):
    await llm.push_frame(
        TextFrame("Let me find the best transit route for you. One moment.")
    )


async def get_bus_route_async(llm, args):
    """
    Async wrapper for get_bus_route so it can be used as a Pipecat tool.
    """
    try:
        gtfs_feed_url = args.get("gtfs_feed_url") or os.getenv("GTFS_FEED_URL")

        result = get_bus_route(
            origin=args["origin"],
            destination=args["destination"],
            gtfs_feed_url=gtfs_feed_url,
        )

        return simplify_for_voice(result)
    except Exception as e:
        logger.error(f"Error getting bus route: {e}")
        return (
            "Sorry, I couldn't find a good transit route right now. "
            "Please try again in a moment."
        )


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

        '''tts = AzureTTSService(
            api_key=os.getenv("AZURE_SPEECH_API_KEY"),
            region=os.getenv("AZURE_REGION"),
        )'''
        stt = DeepgramSTTService(api_key=os.getenv('DEEPGRAM_API_KEY'))

        tts = ElevenLabsTTSService(
                    aiohttp_session=session,
                    api_key=os.getenv("ELEVENLABS_API_KEY"),
                    voice_id=os.getenv("ELEVENLABS_VOICE_ID"),
                )
        
        llm = OpenAILLMService(
            api_key=os.getenv("GROQ_API_KEY"),
            model="llama-3.3-70b-versatile",
            base_url="https://api.groq.com/openai/v1"
        )
        llm.register_function(
            "search_bing",
            search,
            start_callback=start_search)
        llm.register_function(
            "get_bus_route",
            get_bus_route_async,
            start_callback=start_bus_routing,
        )

        tools = get_tools()

        # remove wifi toggle tool
        tools = [tool for tool in tools if tool["function"]["name"] != "toggle_wifi"]

        messages = [
            {
                "role": "system",
                "content": """You are a helpful LLM named Lucy, in a WebRTC call. Your output will be converted to audio so don't include special characters in your answers. 
Respond to what the user said in a creative and helpful way but you love to make witty/bad jokes. Use the tools to help you answer the user such as searching the web.

You will always do what the user asks without hesitation but bring in your personality.
""",
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
