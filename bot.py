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
from common import read_location, write_location

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




def set_location(address: str) -> str:
    """
    Set or update the user's default location (stored in location.json).
    Used by both SMS tool-calls and voice interactions.
    """
    try:
        if not isinstance(address, str) or not address.strip():
            return "Please provide a non-empty address to save as your location."

        write_location({"address": address.strip()})
        return f"Saved your default location as: {address.strip()}."
    except Exception as e:
        logger.error(f"Error saving location: {e}")
        return "Sorry, I couldn't save your location right now. Please try again."

def get_tools():
    location_address = read_location()
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
            },
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
            },
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
                            "description": (
                                "Starting location (address or 'lat,lng'). "
                            ),
                        },
                        "destination": {
                            "type": "string",
                            "description": (
                                "Destination location (address or 'lat,lng'). "
                            ),
                        },
                   
                        "arrive_by": {
                            "type": "string",
                            "description": "Optional arrival time in local time (e.g. '5:30 pm' or '17:30'). If provided, the route will be planned to arrive by this time instead of leaving immediately.",
                        },
                    },
                    "required": ["origin", "destination"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "set_location",
                "description": (
                    "Save or update the user's default location (e.g. '123 Main St, Ottawa, Canada'). "
                    "Future web searches and transit routes will automatically use this as the "
                    "user's default origin / local context where appropriate."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "address": {
                            "type": "string",
                            "description": "The human-readable address to save as the user's default location.",
                        }
                    },
                    "required": ["address"],
                },
            },
        },
    ]


def parse_failed_tool_call(error_str: str):
    """
    Extract function name and args from Groq's failed_generation.
    Example: '<function=search_bing{"query": "Ottawa weather"}</function>'
    Returns (function_name, args_dict) or (None, None)
    """
    try:
        # Extract the failed_generation from error string
        if "'failed_generation':" in error_str:
            start = error_str.find("'failed_generation': '") + len("'failed_generation': '")
            end = error_str.find("'}", start)
            failed_gen = error_str[start:end]
        else:
            return None, None
        
        # Parse: <function=NAME{...}</function>
        if not failed_gen.startswith("<function="):
            return None, None
            
        func_name = failed_gen.split("{")[0].replace("<function=", "")
        json_str = "{" + failed_gen.split("{", 1)[1].replace("</function>", "")
        args = json.loads(json_str)
        
        return func_name, args
    except Exception:
        return None, None

async def handle_tools(messages, tool_calls, from_, to_):
    try:
        available_functions = {
            "search_bing": search_bing,
            "toggle_wifi": toggle_wifi,
            "get_bus_route": get_bus_route,
            "set_location": set_location,
        }

        used_tools = set()

        for tool_call in tool_calls:
            function_name = tool_call.function.name
            used_tools.add(function_name)
            function_to_call = available_functions.get(function_name, None)
            if function_to_call:
                function_args = json.loads(tool_call.function.arguments)
                function_response = function_to_call(**function_args)
                messages.append(
                    {
                        "role": "tool",
                        "content": function_response,
                        "tool_call_id": tool_call.id,
                        "name": function_name,
                    }
                )

        # Ask the model to act purely as a summarizer for SMS.
        # Use different instructions depending on which tool(s) were called.
        if "get_bus_route" in used_tools and used_tools == {"get_bus_route"}:
            # Transit-specific, step-by-step SMS directions.
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "You are composing a single SMS with clear, step-by-step public transit directions "
                        "based ONLY on the previous tool messages from a transit routing tool.\n"
                        "- Start with a one-sentence overview of the trip (total travel time and general route).\n"
                        "- Then give numbered steps that tell the user: when to leave their origin, where to walk "
                        "to catch the first bus (name of the stop or nearby landmark), which bus or train to take "
                        "(route number and name), where to get off, and any transfers.\n"
                        "- Explicitly mention approximately when they should start walking to the stop and how long the "
                        "walking and riding parts take.\n"
                        "- Be concrete and directive, e.g., 'Leave at 5:40 pm, walk 5 minutes to St-Laurent Station, then take bus 97...'\n"
                        "- Do NOT mention tools, snippets, or sources.\n"
                        "- Do NOT use markdown or bullet characters like '*', just plain text with '1)', '2)', etc."
                    ),
                }
            )
        elif "search_bing" in used_tools and used_tools == {"search_bing"}:
            # Web search -> short natural-language answer.
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "You are composing a single SMS reply for the user based ONLY on the previous web search "
                        "tool messages.\n"
                        "- Answer the user's original question directly in natural, conversational language.\n"
                        "- Focus on the single most relevant answer; ignore less important snippets.\n"
                        "- Do NOT include raw snippets, labels like 'WebPage Snippet' or 'Search results', or any URLs.\n"
                        "- Do NOT mention tools, searching, snippets, or sources.\n"
                        "- Do NOT use bullet points, markdown, or formatting characters.\n"
                        "- Keep the answer short and to the point (1–3 sentences)."
                    ),
                }
            )
        else:
            # Fallback: generic tool summarization.
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "You are composing a single SMS reply for the user based ONLY on the previous tool messages.\n"
                        "- Summarize the results in natural, conversational language.\n"
                        "- Do NOT include raw snippets, labels, or URLs.\n"
                        "- Do NOT mention tools, searching, snippets, or sources.\n"
                        "- Do NOT use bullet points, markdown, or formatting characters.\n"
                        "- Keep the answer short and to the point (1–4 sentences)."
                    ),
                }
            )

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
    location_address = read_location()
    location_address_str = location_address['address'] if location_address else "unknown"
    messages = [
        {
            "role": "system",
            "content": (
                "You are an assistant responding to an SMS message. When you need to "
                "search for information or use a tool, call the appropriate function. "
                "Do not wrap function calls in any tags or special formatting."
                f"The user's home address is: {location_address_str}. Use parts of the address in the tool parameters when appropriate. For example, if the user says 'how do I get to this <address>?' then the origin should be the user's home address and the destination should be the <address>."
                "Same for search that relates to locality as well. If the user says 'whats the weather weather now', the query should be 'weather in <city address>'."
            ),
        },
        {
            "role": "user",
            "content": message
        }
    ]
    

    tools = get_tools()


    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            tools=tools
        )
        
        response_message = response.choices[0].message
        tool_calls = response_message.tool_calls
        
        if tool_calls:
            messages.append(response_message)
            return messages, tool_calls
            
        return response_message.content, None
        
    except Exception as e:
        # If Groq fails, try to parse and execute the tool directly
        if hasattr(e, "status_code") and e.status_code == 400:
            func_name, func_args = parse_failed_tool_call(str(e))
            if func_name and func_args:
                available_functions = {
                    "search_bing": search_bing,
                    "toggle_wifi": toggle_wifi,
                    "get_bus_route": get_bus_route,
                    "set_location": set_location,
                }
                fn = available_functions.get(func_name)
                if fn:
                    result = fn(**func_args)
                    return str(result), None
      
        return "Tool call failed. Please try again.", None



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


async def start_set_location(llm):
    await llm.push_frame(
        TextFrame("Got it, I'll save that location for you.")
    )


async def set_location_async(llm, args):
    """
    Async wrapper around set_location so it can be exposed as a Pipecat tool.
    """
    try:
        address = args.get("address", "")
        response = set_location(address)
        return response
    except Exception as e:
        logger.error(f"Error in set_location_async: {e}")
        return "Sorry, I couldn't save your location right now. Please try again."


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
            arrive_by=args.get("arrive_by"),
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
        llm.register_function(
            "set_location",
            set_location_async,
            start_callback=start_set_location,
        )

        tools = get_tools()

        # remove wifi toggle tool
        tools = [tool for tool in tools if tool["function"]["name"] != "toggle_wifi"]

        messages = [
            {
                "role": "system",
                "content": """You are a helpful LLM named Lucy, in a WebRTC call. Your output will be converted to audio so don't include special characters in your answers. 
Respond to what the user said in a creative and helpful way but you love to make witty/bad jokes. Use the tools to help you answer the user such as searching the web.

When you receive search results from the web search tool, ALWAYS summarize them naturally in your own words. Never read out raw snippets or data - instead, extract the key information and present it conversationally.

When you receive a transit route from the get_bus_route tool, give the user clear, step-by-step spoken directions: when to leave, where to walk to catch the bus, which bus or train to take, where to get off, any transfers, and roughly how long the trip will take overall. Make it sound like you are guiding them turn-by-turn.

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
