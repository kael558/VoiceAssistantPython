import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, Response, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from loguru import logger
from pydantic import BaseModel
from starlette.responses import HTMLResponse
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from groq import Groq

from bot import run_bot, handle_tools, choose_tools, format_tool_calls_for_sms, chunk_message
from conversation_manager import add_message, maybe_compress
from common import write_status, read_status, handle_wifi_background_task, load_allowed_numbers, save_allowed_numbers

import asyncio

load_dotenv(override=True)

# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
twilio_client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))

# ---------------------------------------------------------------------------
# Weekly summary config
# ---------------------------------------------------------------------------
WEEKLY_SUMMARY_PHONE = os.getenv("WEEKLY_SUMMARY_PHONE", "")
WEEKLY_SUMMARY_DAY = os.getenv("WEEKLY_SUMMARY_DAY", "sun")
WEEKLY_SUMMARY_HOUR = int(os.getenv("WEEKLY_SUMMARY_HOUR", "10"))
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")

DAY_MAP = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}

# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------
scheduler = None


def _run_weekly_summary():
    """Synchronous wrapper called by APScheduler."""
    if not WEEKLY_SUMMARY_PHONE or not TWILIO_FROM_NUMBER:
        logger.warning("Weekly summary skipped: WEEKLY_SUMMARY_PHONE or TWILIO_FROM_NUMBER not set")
        return
    try:
        from tools.news_summary import send_weekly_summary
        send_weekly_summary(
            llm_client=groq_client,
            twilio_client=twilio_client,
            from_number=TWILIO_FROM_NUMBER,
            to_number=WEEKLY_SUMMARY_PHONE,
        )
    except Exception as e:
        logger.error(f"Weekly summary job failed: {e}")


def _start_scheduler():
    global scheduler
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger

        scheduler = AsyncIOScheduler()
        day = DAY_MAP.get(WEEKLY_SUMMARY_DAY.lower(), 6)
        scheduler.add_job(
            _run_weekly_summary,
            CronTrigger(day_of_week=day, hour=WEEKLY_SUMMARY_HOUR, minute=0),
            id="weekly_summary",
            replace_existing=True,
        )
        scheduler.start()
        day_name = list(DAY_MAP.keys())[day]
        logger.info(f"Weekly summary scheduler started: every {day_name} at {WEEKLY_SUMMARY_HOUR}:00")
    except ImportError:
        logger.warning("APScheduler not installed. Weekly summaries disabled. Run: pip install apscheduler")
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")


async def _init_uber_browser():
    """Try to start the Uber browser session at startup."""
    try:
        from tools.uber_agent import initialize_browser
        result = await initialize_browser()
        logger.info(f"Uber browser init: {result}")
    except ImportError:
        logger.warning("Playwright not installed. Uber automation disabled.")
    except Exception as e:
        logger.warning(f"Uber browser init skipped: {e}")


# ---------------------------------------------------------------------------
# FastAPI lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    write_status(read_status())
    _start_scheduler()
    asyncio.ensure_future(_init_uber_browser())
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# SMS endpoint
# ---------------------------------------------------------------------------
class SMSRequest(BaseModel):
    Body: str
    From: str
    To: str


@app.post("/sms")
async def sms(request: Request, background_tasks: BackgroundTasks):
    resp = MessagingResponse()
    try:
        form = await request.form()
        body = form.get("Body")
        from_ = form.get("From")
        to_ = form.get("To")

        allowed_numbers = load_allowed_numbers()
        if from_ not in allowed_numbers:
            raise HTTPException(status_code=403, detail="Forbidden")

        # Handle adding a new allowed number: "add <number>"
        if body:
            parts = body.strip().split()
            if len(parts) == 2 and parts[0].lower() == "add":
                new_number = parts[1]
                if new_number in allowed_numbers:
                    resp.message(f"{new_number} is already in the allowed numbers list.")
                else:
                    allowed_numbers.append(new_number)
                    save_allowed_numbers(allowed_numbers)
                    resp.message(f"Added {new_number} to the allowed numbers list.")
                return Response(content=str(resp), media_type="application/xml")

        # WiFi toggle shortcut (not stored in conversation)
        if body.lower().strip() == "wifi":
            current_status = read_status()
            if current_status == "toggling":
                resp.message("The WiFi is already being toggled.")
                return Response(content=str(resp), media_type="application/xml")
            resp.message("Toggling Wifi...")
            _ = asyncio.create_task(handle_wifi_background_task())
            return Response(content=str(resp), media_type="application/xml")

        # Save user message to conversation (skip "wifi")
        add_message(from_, "user", body)

        (messages, tool_calls) = choose_tools(body, phone=from_)

        if not tool_calls:
            # Direct LLM response -- save to conversation and reply
            add_message(from_, "assistant", messages)
            maybe_compress(from_, groq_client)
            resp.message(messages)
        else:
            summary_text = format_tool_calls_for_sms(tool_calls)
            resp.message(summary_text)
            _ = asyncio.create_task(
                handle_tools(messages, tool_calls, from_, to_, phone=from_)
            )

        return Response(content=str(resp), media_type="application/xml")

    except HTTPException as he:
        return Response(
            content=str(MessagingResponse().message(he.detail)),
            media_type="application/xml",
            status_code=he.status_code,
        )
    except Exception as e:
        logger.error(f"SMS endpoint error: {e}")
        resp.message(f"An error occurred: {e}")
        return Response(content=str(resp), media_type="application/xml")


# ---------------------------------------------------------------------------
# Voice call endpoints
# ---------------------------------------------------------------------------
@app.post("/start_call")
async def start_call(request: Request):
    try:
        form = await request.form()
        from_ = form.get("From")
        allowed_numbers = load_allowed_numbers()
        if from_ not in allowed_numbers:
            raise HTTPException(status_code=403, detail="Forbidden")
    except Exception:
        raise HTTPException(status_code=403, detail="Forbidden")

    host = request.headers["Host"]
    xml = f"""
    <Response>
      <Connect>
        <Stream url='wss://{host}/ws' />
      </Connect>
    </Response>
    """
    return HTMLResponse(content=xml, media_type="application/xml")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    async for message in websocket.iter_text():
        start_data = json.loads(message)
        if start_data.get("event") == "start":
            stream_sid = start_data["start"]["streamSid"]
            logger.info("WebSocket connection accepted")
            await run_bot(websocket, stream_sid)
            break


# ---------------------------------------------------------------------------
# Manual trigger for weekly summary (for testing)
# ---------------------------------------------------------------------------
@app.post("/trigger_weekly_summary")
async def trigger_weekly_summary():
    if not WEEKLY_SUMMARY_PHONE or not TWILIO_FROM_NUMBER:
        raise HTTPException(
            status_code=400,
            detail="WEEKLY_SUMMARY_PHONE and TWILIO_FROM_NUMBER must be set in .env",
        )
    asyncio.ensure_future(
        asyncio.get_event_loop().run_in_executor(None, _run_weekly_summary)
    )
    return {"status": "Weekly summary triggered"}


if __name__ == "__main__":
    write_status(read_status())
    print("Starting Main Server (SMS/WebSocket) on port 8765...")
    uvicorn.run(app, host="0.0.0.0", port=8765)
