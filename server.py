import json
import os
from datetime import datetime
from typing import Annotated

import uvicorn

from fastapi import FastAPI, WebSocket, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.responses import HTMLResponse
from fastapi.requests import Request

from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from bot import run_bot, handle_tools, choose_tools
import asyncio
from tools.wifi_controller import toggle_wifi


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

allowed_numbers = ['+16138626109', '+16138570911', '+16138570912', '+16139834757']

class SMSRequest(BaseModel):
    Body: str

def write_status(status):
    data = {"wifi_toggle_status": status}
    with open("wifi_status.json", "w") as f:
        json.dump(data, f, indent=4)

def read_status():
    with open("wifi_status.json") as f:
        data = json.load(f)
    return data.get("wifi_toggle_status", "idle")

async def handle_wifi():
    write_status("toggling")
    toggle_wifi()
    write_status("idle")


@app.post('/sms')
async def sms(request: Request):
    resp = MessagingResponse()
    try:
        form = await request.form()
        body = form.get('Body')
        
        from_ = form.get('From')
        if from_ not in allowed_numbers:
            raise HTTPException(status_code=403, details="Forbidden")
        if body.lower().strip() == 'wifi':
	    current_status = read_status()
    	    if current_status == "toggling_started":
        	resp.message("It is already doing it.")
        	return Response(content=str(resp), media_type="application/xml")

	    resp.message('Toggling Wifi...')
       	    _ = asyncio.create_task(handle_wifi())
    	    return Response(content=str(resp), media_type="application/xml"
            
        (messages, tool_calls) = choose_tools(body)
        if not tool_calls:
            # can just return the response
            resp.message(messages)
        else:
            tool_names = [tool_call.function.name for tool_call in tool_calls]
            resp.message("Calling tools: " + ", ".join(tool_names))

            # Start an async task to handle the tools
            # (as they may take longer than 15s limit for twilio webbook)
            
            to_ = form.get('To')
            _ = asyncio.create_task(handle_tools(messages, tool_calls, from_, to_))

        #print("Response sent", str(resp))
        return Response(content=str(resp), media_type="application/xml")
    except Exception as e:
        resp.message(f"An error occurred {e}")
        return Response(content=str(resp), media_type="application/xml")


@app.post('/start_call')
async def start_call(request: Request):
    try:
        form = await request.form()

        from_ = form.get('From')
        if from_ not in allowed_numbers:
            raise HTTPException(status_code=403, details="Forbidden")
    except:
        raise HTTPException(status_code=403, details="Forbidden")
            
    host = request.headers['Host']
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="wss://{host}/ws"></Stream>
  </Connect>
  <Pause length="40"/>
</Response>"""

    return HTMLResponse(content=xml, media_type="application/xml")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    start_data = websocket.iter_text()
    await start_data.__anext__()
    call_data = json.loads(await start_data.__anext__())
    print(call_data, flush=True)
    stream_sid = call_data['start']['streamSid']
    print("WebSocket connection accepted")
    await run_bot(websocket, stream_sid)


if __name__ == "__main__":
    #toggle_wifi()
    uvicorn.run(app, host="0.0.0.0", port=8765)
