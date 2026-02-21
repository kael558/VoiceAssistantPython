#
# Copyright (c) 2024, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#
import json
import os
import sys
import time
import asyncio

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
from pipecat.services.deepgram import DeepgramSTTService
from pipecat.services.openai import OpenAILLMContext, OpenAILLMService
from pipecat.transports.network.fastapi_websocket import FastAPIWebsocketTransport, FastAPIWebsocketParams
from pipecat.vad.silero import SileroVADAnalyzer
from twilio.rest import Client

from tools.web_search import search_web, search_local
from tools.firecrawl_scraper import scrape_url
from tools.wifi_controller import toggle_wifi
from tools.bus_router_transit import get_transit_route
from tools.uber_agent import book_uber, uber_status, cancel_uber, add_uber_stop, start_ride_monitor
from common import read_location, write_location
from conversation_manager import (
    add_message,
    build_llm_context,
    maybe_compress,
)

from groq import Groq

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")

client = Groq(
    api_key=os.environ.get("GROQ_API_KEY"),
)

account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
twilio_client = Client(account_sid, auth_token)


def set_location(address: str) -> str:
    try:
        if not isinstance(address, str) or not address.strip():
            return "Please provide a non-empty address to save as your location."
        write_location(address.strip())
        return f"Saved your default location as: {address.strip()}."
    except Exception as e:
        logger.error(f"Error saving location: {e}")
        return "Sorry, I couldn't save your location right now. Please try again."


def chunk_message(text: str, max_len: int = 1600) -> list[str]:
    if not text:
        return []
    return [text[i : i + max_len] for i in range(0, len(text), max_len)]


def send_sms(body: str, from_: str, to: str) -> None:
    """Send a single SMS via Twilio. Used by the ride monitor and elsewhere."""
    twilio_client.messages.create(body=body, from_=from_, to=to)


def format_tool_calls_for_sms(tool_calls) -> str:
    if not tool_calls:
        return "Working on your request..."

    lines: list[str] = []
    total = len(tool_calls)
    header = f"Tools running ({total})" if total > 1 else "Tool running"
    lines.append(f"=== {header} ===")

    for idx, tool_call in enumerate(tool_calls, start=1):
        name = getattr(getattr(tool_call, "function", None), "name", None) or "unknown_tool"
        raw_args = getattr(getattr(tool_call, "function", None), "arguments", "{}") or "{}"

        try:
            args = json.loads(raw_args)
        except Exception:
            args = {}

        lines.append(f"{idx}. {name}")
        detail_lines: list[str] = []

        if name == "get_transit_route":
            for key in ("origin", "destination", "arrive_by"):
                if args.get(key):
                    detail_lines.append(f"{key.replace('_', ' ').title()}: {args[key]}")
        elif name in ("search_web", "search_local"):
            if args.get("query"):
                detail_lines.append(f"Query: {args['query']}")
        elif name == "scrape_url":
            if args.get("url"):
                detail_lines.append(f"URL: {args['url']}")
        elif name == "book_uber":
            if args.get("destination"):
                detail_lines.append(f"Destination: {args['destination']}")
            if args.get("pickup"):
                detail_lines.append(f"Pickup: {args['pickup']}")
        elif name == "add_uber_stop":
            if args.get("stop_address"):
                detail_lines.append(f"Stop: {args['stop_address']}")
        elif name in ("uber_status", "cancel_uber", "toggle_wifi"):
            detail_lines.append("No parameters")
        elif name == "set_location":
            if args.get("address"):
                detail_lines.append(f"Address: {args['address']}")
        else:
            for key, value in args.items():
                detail_lines.append(f"{key}: {value}")

        for detail in detail_lines:
            lines.append(f"   - {detail}")
        lines.append("")

    while lines and lines[-1] == "":
        lines.pop()
    lines.append("")
    lines.append("====================")
    return "\n".join(lines)


def get_tools():
    return [
        {
            "type": "function",
            "function": {
                "name": "search_web",
                "description": (
                    "Search the web for real-time information, current events, weather, "
                    "news, or any factual query that requires up-to-date data. "
                    "Use this for general knowledge queries like 'latest iPhone specs', "
                    "'weather in Ottawa', 'who won the game last night', etc."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query",
                        },
                        "location": {
                            "type": "string",
                            "description": "Optional geographic context for the search (e.g. 'Ottawa, Ontario')",
                        },
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_local",
                "description": (
                    "Search for local places, businesses, and services near a location. "
                    "Use this when the user asks about nearby places like 'staffing agencies near me', "
                    "'best restaurants around here', 'gas stations nearby', 'pharmacies in Ottawa', etc. "
                    "Returns a list of places with names, addresses, ratings, phone numbers, and a map."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "What to search for (e.g. 'staffing agencies', 'Italian restaurants')",
                        },
                        "location": {
                            "type": "string",
                            "description": "The location to search near (e.g. 'Ottawa, ON' or '123 Main St, Ottawa')",
                        },
                    },
                    "required": ["query", "location"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "scrape_url",
                "description": (
                    "Scrape and read the content of a specific URL/webpage. "
                    "Use this when the user asks you to read a webpage, article, or document at a specific URL, "
                    "or when you need deeper information from a search result."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "The full URL to scrape (e.g. 'https://example.com/article')",
                        },
                    },
                    "required": ["url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "toggle_wifi",
                "description": "Toggle the WiFi on or off.",
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
                "description": (
                    "Find the best public transit route (bus/train/metro) between two locations. "
                    "Uses Google Maps and optional real-time vehicle positions."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "origin": {
                            "type": "string",
                            "description": "Starting location (address or 'lat,lng').",
                        },
                        "destination": {
                            "type": "string",
                            "description": "Destination location (address or 'lat,lng').",
                        },
                        "arrive_by": {
                            "type": "string",
                            "description": "Optional arrival time (e.g. '5:30 pm' or '17:30').",
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
                    "Save or update the user's default home location. "
                    "Future searches and transit routes will use this as the default origin."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "address": {
                            "type": "string",
                            "description": "The address to save (e.g. '123 Main St, Ottawa, Canada').",
                        },
                    },
                    "required": ["address"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "book_uber",
                "description": (
                    "Book an Uber ride to a destination. After booking, the user will "
                    "receive SMS updates with driver info, vehicle, plate number, and ETA."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "destination": {
                            "type": "string",
                            "description": "Where to go (address or place name).",
                        },
                        "pickup": {
                            "type": "string",
                            "description": "Optional pickup location. Defaults to user's saved location.",
                        },
                    },
                    "required": ["destination"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "uber_status",
                "description": "Check the current status of an active Uber ride (driver name, vehicle, plate, ETA).",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "cancel_uber",
                "description": "Cancel the current active Uber ride.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "add_uber_stop",
                "description": "Add an additional stop to the current Uber ride.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "stop_address": {
                            "type": "string",
                            "description": "The address of the stop to add.",
                        },
                    },
                    "required": ["stop_address"],
                },
            },
        },
    ]


def _get_sms_system_prompt(location_address: str) -> str:
    return (
        "You are Lucy, a helpful personal assistant responding via SMS. "
        "You are conversational, concise, and occasionally witty.\n\n"
        "IMPORTANT RULES:\n"
        "- If you can answer a question from your own general knowledge (e.g. 'what is photosynthesis', "
        "'who is the president of France', 'how do I make pasta'), answer DIRECTLY without using any tools.\n"
        "- Only use tools when you need real-time, up-to-date, or location-specific information.\n"
        "- When a user asks about nearby places/businesses, use search_local.\n"
        "- When a user asks about current events, weather, or needs real-time data, use search_web.\n"
        "- When a user gives a URL to read, use scrape_url.\n"
        "- When a user wants to book/check/cancel an Uber, use the uber tools.\n"
        "- Do not wrap function calls in any tags or special formatting.\n\n"
        f"The user's home address is: {location_address}. "
        "Use parts of the address in tool parameters when appropriate. "
        "For example, if the user says 'how do I get to <address>?' then the origin should be "
        "the user's home address. For local searches, use the city from their address."
    )


def parse_failed_tool_call(error_str: str):
    try:
        if "'failed_generation':" in error_str:
            start = error_str.find("'failed_generation': '") + len("'failed_generation': '")
            end = error_str.find("'}", start)
            failed_gen = error_str[start:end]
        else:
            return None, None

        if not failed_gen.startswith("<function="):
            return None, None

        func_name = failed_gen.split("{")[0].replace("<function=", "")
        json_str = "{" + failed_gen.split("{", 1)[1].replace("</function>", "")
        args = json.loads(json_str)
        return func_name, args
    except Exception:
        return None, None


AVAILABLE_FUNCTIONS = {
    "search_web": search_web,
    "search_local": search_local,
    "scrape_url": scrape_url,
    "toggle_wifi": toggle_wifi,
    "get_transit_route": get_transit_route,
    "set_location": set_location,
    "book_uber": book_uber,
    "uber_status": uber_status,
    "cancel_uber": cancel_uber,
    "add_uber_stop": add_uber_stop,
}


async def handle_tools(messages, tool_calls, from_, to_, phone=None):
    try:
        used_tools = set()
        map_url = None

        for tool_call in tool_calls:
            function_name = tool_call.function.name
            used_tools.add(function_name)
            function_to_call = AVAILABLE_FUNCTIONS.get(function_name)
            if not function_to_call:
                continue

            function_args = json.loads(tool_call.function.arguments)
            function_response = function_to_call(**function_args)

            # search_local returns a dict with "text" and "map_url"
            if function_name == "search_local" and isinstance(function_response, dict):
                map_url = function_response.get("map_url")
                function_response = function_response["text"]

            # Ensure response is a string for the tool message
            if not isinstance(function_response, str):
                function_response = json.dumps(function_response)

            messages.append({
                "role": "tool",
                "content": function_response,
                "tool_call_id": tool_call.id,
                "name": function_name,
            })

        # Start Uber ride monitoring if a ride was booked
        if "book_uber" in used_tools:
            asyncio.ensure_future(start_ride_monitor(send_sms, to_, from_))

        # Build summarization prompt based on which tools were used
        if "get_transit_route" in used_tools:
            messages.append({
                "role": "system",
                "content": (
                    "You are composing a single SMS with clear public transit directions "
                    "based ONLY on the previous tool messages. "
                    "Pass on the tool output as-is unless it is unclear. "
                    "Do not invent stop names, numbers, or times."
                ),
            })
        elif "search_local" in used_tools:
            messages.append({
                "role": "system",
                "content": (
                    "You are composing an SMS reply listing local places/businesses. "
                    "Present the results as a clean numbered list with name, address, rating, and phone. "
                    "Be concise but include all the key details. Do NOT use markdown. "
                    "Do NOT include URLs. Do NOT mention tools or searching."
                ),
            })
        elif "search_web" in used_tools:
            messages.append({
                "role": "system",
                "content": (
                    "You are composing a single SMS reply based on web search results.\n"
                    "- Answer the user's question directly in natural, conversational language.\n"
                    "- Extract and present the key information clearly.\n"
                    "- Do NOT include raw snippets, labels like 'Search results', or URLs.\n"
                    "- Do NOT mention tools, searching, snippets, or sources.\n"
                    "- Do NOT use markdown or special formatting.\n"
                    "- Keep it concise (1-4 sentences for simple questions, more for complex ones)."
                ),
            })
        elif "scrape_url" in used_tools:
            messages.append({
                "role": "system",
                "content": (
                    "You are composing an SMS reply summarizing the webpage content. "
                    "Provide a clear, concise summary of the most important information. "
                    "Do NOT use markdown. Keep it under 1500 characters."
                ),
            })
        elif any(t in used_tools for t in ("book_uber", "uber_status", "cancel_uber", "add_uber_stop")):
            messages.append({
                "role": "system",
                "content": (
                    "You are composing an SMS reply about the user's Uber ride. "
                    "Relay the ride information clearly and concisely. "
                    "Include all relevant details (driver, vehicle, plate, ETA, status)."
                ),
            })
        else:
            messages.append({
                "role": "system",
                "content": (
                    "You are composing a single SMS reply based on the tool results.\n"
                    "- Summarize in natural, conversational language.\n"
                    "- Do NOT include raw data, labels, or URLs.\n"
                    "- Do NOT use markdown.\n"
                    "- Keep the answer short (1-4 sentences)."
                ),
            })

        second_response = client.chat.completions.create(
            messages=messages,
            model="llama-3.3-70b-versatile",
        )
        full_body = second_response.choices[0].message.content

        # Save assistant response to conversation
        if phone:
            add_message(phone, "assistant", full_body)
            maybe_compress(phone, client)

        # Send the response as SMS (with optional MMS map image)
        parts = chunk_message(full_body, 1600)
        for i, part in enumerate(parts):
            if i > 0:
                time.sleep(1)
            kwargs = {"body": part, "from_": to_, "to": from_}
            # Attach map image to the first message if available
            if i == 0 and map_url:
                kwargs["media_url"] = [map_url]
            twilio_client.messages.create(**kwargs)

    except Exception as e:
        logger.error(f"handle_tools error: {e}")
        error_body = f"Sorry, something went wrong: {e}"
        error_parts = chunk_message(error_body, 1600)
        for i, part in enumerate(error_parts):
            if i > 0:
                time.sleep(1)
            twilio_client.messages.create(body=part, from_=to_, to=from_)


def choose_tools(message, phone=None):
    location_address = read_location()
    system_prompt = _get_sms_system_prompt(location_address)

    if phone:
        messages = build_llm_context(phone, system_prompt)
    else:
        messages = [{"role": "system", "content": system_prompt}]

    messages.append({"role": "user", "content": message})

    tools = get_tools()

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            tools=tools,
        )

        response_message = response.choices[0].message
        tool_calls = response_message.tool_calls

        if tool_calls:
            messages.append(response_message)
            return messages, tool_calls

        # Direct LLM response (no tools needed)
        return response_message.content, None

    except Exception as e:
        if hasattr(e, "status_code") and e.status_code == 400:
            func_name, func_args = parse_failed_tool_call(str(e))
            if func_name and func_args:
                fn = AVAILABLE_FUNCTIONS.get(func_name)
                if fn:
                    result = fn(**func_args)
                    if isinstance(result, dict):
                        return str(result.get("text", result)), None
                    return str(result), None

        logger.error(f"choose_tools error: {e}")
        return "Sorry, I couldn't process that. Please try again.", None


# ---------------------------------------------------------------------------
# Voice bot helpers (Pipecat)
# ---------------------------------------------------------------------------

async def start_search(llm):
    await llm.push_frame(TextFrame("Let me search for that. Give me one second."))


async def search_voice(llm, args):
    """Voice wrapper for web search."""
    try:
        return search_web(args["query"])
    except Exception as e:
        logger.error(f"Voice search error: {e}")
        return "Failed to retrieve search results"


def simplify_for_voice(text: str) -> str:
    emojis_to_remove = ["🚌", "📍", "⏱️", "📊", "✅", "🔴", "⬜", "🗺️"]
    for emoji in emojis_to_remove:
        text = text.replace(emoji, "")
    for ch in ["=", "-", "_"]:
        text = text.replace(ch * 2, " ")
    text = text.replace("~", " approximately ")
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
    try:
        address = args.get("address", "")
        response = set_location(address)
        return response
    except Exception as e:
        logger.error(f"Error in set_location_async: {e}")
        return "Sorry, I couldn't save your location right now. Please try again."


async def get_transit_route_async(llm, args):
    try:
        result = get_transit_route(
            origin=args["origin"],
            destination=args["destination"],
            arrive_by=args.get("arrive_by"),
        )
        return simplify_for_voice(result)
    except Exception as e:
        logger.error(f"Error getting bus route: {e}")
        return "Sorry, I couldn't find a good transit route right now. Please try again in a moment."


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
                serializer=TwilioFrameSerializer(stream_sid),
            ),
        )

        stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

        tts = ElevenLabsTTSService(
            aiohttp_session=session,
            api_key=os.getenv("ELEVENLABS_API_KEY"),
            voice_id=os.getenv("ELEVENLABS_VOICE_ID"),
        )

        llm = OpenAILLMService(
            api_key=os.getenv("GROQ_API_KEY"),
            model="llama-3.3-70b-versatile",
            base_url="https://api.groq.com/openai/v1",
        )
        llm.register_function(
            "search_web",
            search_voice,
            start_callback=start_search,
        )
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
        # Voice doesn't use wifi, uber, scrape, or local search tools
        voice_tool_names = {"search_web", "get_transit_route", "set_location"}
        tools = [t for t in tools if t["function"]["name"] in voice_tool_names]

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful LLM named Lucy, in a WebRTC call. Your output will be "
                    "converted to audio so don't include special characters in your answers.\n"
                    "Respond to what the user said in a creative and helpful way but you love to "
                    "make witty/bad jokes. Use the tools to help you answer the user such as "
                    "searching the web.\n\n"
                    "IMPORTANT: If you can answer a question from your own general knowledge, "
                    "answer DIRECTLY without using any tools. Only use tools for real-time or "
                    "location-specific information.\n\n"
                    "When you receive search results from the web search tool, ALWAYS summarize them "
                    "naturally in your own words. Never read out raw snippets or data.\n\n"
                    "When you receive a transit route from the get_transit_route tool, give the user "
                    "clear, step-by-step spoken directions.\n\n"
                    "You will always do what the user asks without hesitation but bring in your personality."
                ),
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
            tma_out,
        ])

        task = PipelineTask(pipeline, params=PipelineParams(allow_interruptions=True))

        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            logger.info("Client connected.")
            messages.append(
                {"role": "system", "content": "Please introduce yourself to the user."}
            )
            await task.queue_frames([LLMMessagesFrame(messages)])

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport, client):
            await task.queue_frames([EndFrame()])

        runner = PipelineRunner(handle_sigint=False)
        await runner.run(task)
