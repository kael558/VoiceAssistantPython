import json
import os
from datetime import datetime
from typing import Annotated
import uvicorn
from fastapi import FastAPI, WebSocket, Response, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.responses import HTMLResponse, PlainTextResponse, JSONResponse
from fastapi.requests import Request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from bot import run_bot, handle_tools, choose_tools
import asyncio
from common import write_status, read_status, handle_wifi_background_task

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

allowed_numbers = ['+16138626109', '+16138570911', '+16138570912', '+16139834757']

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

        if from_ not in allowed_numbers:
            raise HTTPException(status_code=403, detail="Forbidden")

        if body.lower().strip() == 'wifi':
            current_status = read_status()
            if current_status == "toggling":
                resp.message("It is already doing it.")
                return Response(content=str(resp), media_type="application/xml")
            resp.message('Toggling Wifi...')
            background_tasks.add_task(handle_wifi_background_task)
            return Response(content=str(resp), media_type="application/xml")

        (messages, tool_calls) = choose_tools(body)
        if not tool_calls:
            resp.message(messages)
        else:
            tool_names = [tool_call.function.name for tool_call in tool_calls]
            resp.message("Calling tools: " + ", ".join(tool_names))
            background_tasks.add_task(handle_tools, messages, tool_calls, from_, to_)
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
    read_names_status()
    print("Starting Main Server (SMS/WebSocket) on port 8765...")
    uvicorn.run(app, host="0.0.0.0", port=8765)
