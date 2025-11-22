#
# Copyright (c) 2024, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#
import json
import os
import sys
import time

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
from tools.bus_router_transit import get_transit_route
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
def chunk_message(text: str, max_len: int = 1600) -> list[str]:
    """
    Naively split text into chunks of at most `max_len` characters.
    This does NOT try to preserve whole words; it just slices the string.
    """
    if not text:
        return []

    return [text[i : i + max_len] for i in range(0, len(text), max_len)]


def format_tool_calls_for_sms(tool_calls) -> str:
    """
    Create a concise, SMS-friendly summary of the tools being called
    and their parameters.
    """
    if not tool_calls:
        return "Working on your request… (running tools)"

    lines: list[str] = []
    total = len(tool_calls)
    header = f"Tools running ({total})" if total > 1 else "Tool running"

    # Visual header
    lines.append(f"=== {header} ===")


    for idx, tool_call in enumerate(tool_calls, start=1):
        name = getattr(getattr(tool_call, "function", None), "name", None) or "unknown_tool"
        raw_args = getattr(getattr(tool_call, "function", None), "arguments", "{}") or "{}"

        try:
            args = json.loads(raw_args)
        except Exception:
            args = {}

        # Tool name header with index
        lines.append(f"{idx}. {name}")

        # Collect pretty-printed argument lines for this tool
        detail_lines: list[str] = []

        if name == "get_transit_route":
            origin = args.get("origin")
            destination = args.get("destination")
            arrive_by = args.get("arrive_by")

            if origin:
                detail_lines.append(f"Origin: {origin}")
            if destination:
                detail_lines.append(f"Destination: {destination}")
            if arrive_by:
                detail_lines.append(f"Arrive by: {arrive_by}")

        elif name == "search_bing":
            query = args.get("query")
            if query:
                detail_lines.append(f"Query: {query}")

        elif name == "set_location":
            address = args.get("address")
            if address:
                detail_lines.append(f"Address: {address}")

        elif name == "toggle_wifi":
            detail_lines.append("No parameters")

        else:
            # Generic fallback: list key/value pairs
            for key, value in args.items():
                detail_lines.append(f"{key}: {value}")

        # Add the detail lines with a bullet and indentation
        for detail in detail_lines:
            lines.append(f"   • {detail}")

        # Spacer line between tools
        lines.append("")

    # Trim any trailing blank lines
    while lines and lines[-1] == "":
        lines.pop()

    # Add a simple footer
    lines.append("")
    lines.append("====================")

    return "\n".join(lines)

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
                "name": "get_transit_route",
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
            "get_transit_route": get_transit_route,
            "set_location": set_location,
        }

        used_tools = set()

        print(tool_calls)

        for tool_call in tool_calls:
            function_name = tool_call.function.name
            used_tools.add(function_name)
            function_to_call = available_functions.get(function_name, None)
            if function_to_call:
                function_args = json.loads(tool_call.function.arguments)
                print(function_name)
                print(function_args)
                function_response = function_to_call(**function_args)
                messages.append(
                    {
                        "role": "tool",
                        "content": function_response,
                        "tool_call_id": tool_call.id,
                        "name": function_name,
                    }
                )
                print(function_response)
                print("--------------------------------")

        # Ask the model to act purely as a summarizer for SMS.
        # Use different instructions depending on which tool(s) were called.
        if "get_transit_route" in used_tools and used_tools == {"get_transit_route"}:
            # Transit-specific, SMS directions in a fixed simple, newline-separated template.
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "You are composing a single SMS with clear public transit directions "
                        "based ONLY on the previous tool messages from a transit routing tool.\n"
                        "Follow EXACTLY this simple, newline-separated template, using only information that is clearly present "
                        "in the tool output (do not invent stop names, numbers, or times):\n"
                        "\n"
                        "- Leave at <departure time from origin>\n"
                        "- Take bus <bus number or line name> heading in <headsign or destination> direction from stop <stop name> (stop number <stop id if given>) from <intersection>, leaving at <scheduled or estimated departure time>\n"
                        "- Get off at <arrival stop>; if the tool output clearly provides the stop just before this, add: 'The stop just before your stop is <previous stop name>'; otherwise omit this part rather than guessing\n"
                        "- You will arrive at <approximate arrival time and total travel time>\n"
                        "- Walking: briefly describe basic walking directions and approximate walking times to the first stop and between any transfers, in 1–3 short sentences\n"
                        "\n"
                        "Additional rules:\n"
                        "- Use plain text only; keep it under 3–6 short lines as shown above.\n"
                        "- Do NOT mention tools, searching, snippets, or sources.\n"
                        "- Do NOT add extra commentary before or after the template; only output the lines in this format."
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
        full_body = second_response.choices[0].message.content
        parts = chunk_message(full_body, 1600)
        for i, part in enumerate(parts):
            # Add a small delay between messages to avoid spamming
            if i > 0:
                time.sleep(1)
            twilio_client.messages.create(
                body=part,
                from_=to_,
                to=from_
            )
    except Exception as e:
        logger.error(f"Error: {e}")
        error_body = f"An error occurred {e}"
        error_parts = chunk_message(error_body, 1600)
        for i, part in enumerate(error_parts):
            if i > 0:
                time.sleep(1)
            twilio_client.messages.create(
                body=part,
                from_=to_,
                to=from_
            )



def choose_tools(message):
    location_address = read_location()

    messages = [
        {
            "role": "system",
            "content": (
                "You are an assistant responding to an SMS message. When you need to "
                "search for information or use a tool, call the appropriate function. "
                "Do not wrap function calls in any tags or special formatting."
                f"The user's home address is: {location_address}. Use parts of the address in the tool parameters when appropriate. For example, if the user says 'how do I get to this <address>?' then the origin should be the user's home address and the destination should be the <address>."
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
                    "get_transit_route": get_transit_route,
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


async def get_transit_route_async(llm, args):
    """
    Async wrapper for get_transit_route so it can be used as a Pipecat tool.
    """
    try:
        gtfs_feed_url = args.get("gtfs_feed_url") or os.getenv("GTFS_FEED_URL")

        result = get_transit_route(
            origin=args["origin"],
            destination=args["destination"],
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
            "get_transit_route",
            get_transit_route_async,
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

When you receive a transit route from the get_transit_route tool, give the user clear, step-by-step spoken directions: when to leave, where to walk to catch the bus, which bus or train to take, where to get off, any transfers, and roughly how long the trip will take overall. Make it sound like you are guiding them turn-by-turn.

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
