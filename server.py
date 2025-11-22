import json
import os
from datetime import datetime
from typing import Annotated, List
import uvicorn
from fastapi import FastAPI, WebSocket, Response, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.responses import HTMLResponse, PlainTextResponse, JSONResponse
from fastapi.requests import Request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from bot import run_bot, handle_tools, choose_tools, format_tool_calls_for_sms
import asyncio
from common import write_status, read_status, handle_wifi_background_task, load_allowed_numbers, save_allowed_numbers
from json import JSONDecodeError

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic models for request bodies ---
class SMSRequest(BaseModel):
    Body: str
    From: str
    To: str

# --- SMS related endpoints ---
@app.post('/sms')
async def sms(request: Request, background_tasks: BackgroundTasks):
    resp = MessagingResponse()
    try:
        form = await request.form()
        body = form.get('Body')
        from_ = form.get('From')
        to_ = form.get('To')

        allowed_numbers = load_allowed_numbers()

        if from_ not in allowed_numbers:
            raise HTTPException(status_code=403, detail="Forbidden")

        # Handle adding a new allowed number via SMS: "add <number>"
        if body:
            parts = body.strip().split()
            if len(parts) == 2 and parts[0].lower() == 'add':
                new_number = parts[1]
                if new_number in allowed_numbers:
                    resp.message(f"{new_number} is already in the allowed numbers list.")
                else:
                    allowed_numbers.append(new_number)
                    save_allowed_numbers(allowed_numbers)
                    resp.message(f"Added {new_number} to the allowed numbers list.")
                return Response(content=str(resp), media_type="application/xml")

        if body.lower().strip() == 'wifi':
            current_status = read_status()
            if current_status == "toggling":
                resp.message("The WiFi is already being toggled.")
                return Response(content=str(resp), media_type="application/xml")
            resp.message('Toggling Wifi...')
            _ = asyncio.create_task(handle_wifi_background_task())  # Changed to asyncio.create_task
            return Response(content=str(resp), media_type="application/xml")

        (messages, tool_calls) = choose_tools(body)
        if not tool_calls:
            resp.message(messages)
        else:
            # Send a nicely formatted summary of the tools being called,
            # including key parameters, so the user can see exactly
            # what is happening.
            summary_text = format_tool_calls_for_sms(tool_calls)
            resp.message(summary_text)
            _ = asyncio.create_task(handle_tools(messages, tool_calls, from_, to_))
        return Response(content=str(resp), media_type="application/xml")
    except HTTPException as he:
        return Response(content=str(MessagingResponse().message(he.detail)), media_type="application/xml", status_code=he.status_code)
    except Exception as e:
        resp.message(f"An error occurred {e}")
        return Response(content=str(resp), media_type="application/xml")





@app.post('/start_call')
async def start_call(request: Request):
    try:
        form = await request.form()
        from_ = form.get('From')
        allowed_numbers = load_allowed_numbers()
        if from_ not in allowed_numbers:
            raise HTTPException(status_code=403, detail="Forbidden")
    except Exception: # Catch any exception during form parsing/access
        raise HTTPException(status_code=403, detail="Forbidden")
    
    host = request.headers['Host']
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
    # Using async for for iter_text to properly handle the stream
    async for message in websocket.iter_text():
        start_data = json.loads(message)
        if start_data.get('event') == 'start':
            stream_sid = start_data['start']['streamSid']
            print("WebSocket connection accepted")
            await run_bot(websocket, stream_sid)
            break # Exit the loop once start event is processed and bot is running

if __name__ == "__main__":
    # Ensure initial status files exist
    write_status(read_status())
    print("Starting Main Server (SMS/WebSocket) on port 8765...")
    uvicorn.run(app, host="0.0.0.0", port=8765)
