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
from tools.wifi_controller import toggle_wifi
from fastapi.responses import RedirectResponse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

allowed_numbers = ['+16138626109', '+16138570911', '+16138570912', '+16139834757']

# --- Common functions for status files ---
def write_status(status):
    try:
        data = {"wifi_toggle_status": status}
        with open("wifi_status.json", "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error writing status: {e}")

def read_status():
    try:
        with open("wifi_status.json", "r") as f:
            data = json.load(f)
        return data.get("wifi_toggle_status", "idle")
    except FileNotFoundError:
        write_status("idle")
        return "idle"
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
        write_status("idle")
        return "idle"
    except Exception as e:
        print(f"Error reading status: {e}")
        return "idle"

def read_names_status():
    try:
        with open("names_status.json") as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        # Default names
        default_data = {
            "names": ["Alice", "Bob", "Charlie", "Diana"],
            "toggles": {"Alice": False, "Bob": False, "Charlie": False, "Diana": False}
        }
        write_names_status(default_data)
        return default_data

def write_names_status(data):
    with open("names_status.json", "w") as f:
        json.dump(data, f, indent=4)

# --- Pydantic models for request bodies ---
class SMSRequest(BaseModel):
    Body: str
    From: str
    To: str

class NameToggle(BaseModel):
    name: str

class AddName(BaseModel):
    name: str

class RemoveName(BaseModel):
    name: str

# --- SMS related endpoints (from first server) ---
async def handle_wifi_background_task():
    write_status("toggling")
    toggle_wifi()
    write_status("idle")

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
            if current_status == "toggling": # Corrected from "toggling_started"
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

# --- Web UI related endpoints (from second server) ---
@app.get("/web")
async def web():
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
      <title>WiFi Neural Network Controller</title>
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <style>
        * {
          margin: 0;
          padding: 0;
          box-sizing: border-box;
        }
        
        body {
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
          background: #f5f5f5;
          color: #333;
          line-height: 1.6;
          padding: 20px;
        }
        
        .container {
          max-width: 1000px;
          margin: 0 auto;
        }
        
        .header {
          text-align: center;
          margin-bottom: 30px;
          background: white;
          border-radius: 8px;
          padding: 30px;
          box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        
        .header h1 {
          font-size: 2.5em;
          margin-bottom: 10px;
          color: #2c3e50;
        }
        
        .header p {
          color: #7f8c8d;
          font-size: 1.1em;
        }
        
        .main-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 20px;
          margin-bottom: 20px;
        }
        
        .card {
          background: white;
          border-radius: 8px;
          padding: 25px;
          box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        
        .card h2 {
          font-size: 1.5em;
          margin-bottom: 20px;
          color: #2c3e50;
        }
        
        .wifi-button {
          width: 100%;
          padding: 15px;
          font-size: 1.2em;
          font-weight: 600;
          background: #3498db;
          color: white;
          border: none;
          border-radius: 6px;
          cursor: pointer;
          transition: background 0.3s ease;
        }
        
        .wifi-button:hover:not(:disabled) {
          background: #2980b9;
        }
        
        .wifi-button:disabled {
          background: #bdc3c7;
          cursor: not-allowed;
        }
        
        .status {
          text-align: center;
          font-size: 1.1em;
          margin-top: 15px;
          color: #27ae60;
        }
        
        .status.toggling {
          color: #e67e22;
          font-weight: 600;
        }
        
        .name-item {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 12px;
          margin: 8px 0;
          background: #ecf0f1;
          border-radius: 6px;
        }
        
        .name-text {
          font-size: 1em;
          font-weight: 500;
        }
        
        .name-controls {
          display: flex;
          align-items: center;
          gap: 10px;
        }
        
        .toggle-switch {
          position: relative;
          width: 50px;
          height: 25px;
          background: #bdc3c7;
          border-radius: 15px;
          cursor: pointer;
          transition: background 0.3s;
        }
        
        .toggle-switch.active {
          background: #27ae60;
        }
        
        .toggle-slider {
          position: absolute;
          top: 2px;
          left: 2px;
          width: 21px;
          height: 21px;
          background: white;
          border-radius: 50%;
          transition: transform 0.3s;
          box-shadow: 0 1px 3px rgba(0,0,0,0.3);
        }
        
        .toggle-switch.active .toggle-slider {
          transform: translateX(25px);
        }
        
        .remove-btn {
          background: #e74c3c;
          color: white;
          border: none;
          padding: 6px 12px;
          border-radius: 4px;
          cursor: pointer;
          font-size: 0.85em;
          transition: background 0.3s ease;
        }
        
        .remove-btn:hover {
          background: #c0392b;
        }
        
        .management-controls {
          display: flex;
          gap: 10px;
          margin-top: 15px;
        }
        
        .ctrl-input {
          flex: 1;
          padding: 10px;
          border: 2px solid #bdc3c7;
          border-radius: 4px;
          font-size: 1em;
        }
        
        .ctrl-input:focus {
          outline: none;
          border-color: #3498db;
        }
        
        .ctrl-btn {
          padding: 10px 15px;
          background: #27ae60;
          color: white;
          border: none;
          border-radius: 4px;
          cursor: pointer;
          font-size: 1em;
          transition: background 0.3s ease;
        }
        
        .ctrl-btn:hover {
          background: #219a52;
        }
        
        .progress-bar {
          width: 100%;
          height: 8px;
          background: #ecf0f1;
          border-radius: 4px;
          overflow: hidden;
          margin-top: 15px;
        }
        
        .progress-fill {
          height: 100%;
          background: #3498db;
          border-radius: 4px;
          transition: width 0.3s ease;
        }
        
        .progress-text {
          text-align: center;
          margin-top: 8px;
          font-size: 0.9em;
          color: #7f8c8d;
        }
        
        .log {
          background: #2c3e50;
          color: #ecf0f1;
          padding: 15px;
          height: 250px;
          overflow-y: auto;
          border-radius: 6px;
          font-family: 'Courier New', monospace;
          white-space: pre-wrap;
          font-size: 0.9em;
        }
        
        /* Tablet Responsive - 768px and below */
        @media (max-width: 768px) {
          body {
            padding: 15px;
          }
          
          .container {
            max-width: 100%;
          }
          
          .main-grid {
            grid-template-columns: 1fr;
            gap: 20px;
          }
          
          .header {
            padding: 25px 20px;
          }
          
          .header h1 {
            font-size: 2.2em;
          }
          
          .header p {
            font-size: 1em;
          }
          
          .card {
            padding: 20px;
          }
          
          .card h2 {
            font-size: 1.4em;
          }
          
          .wifi-button {
            font-size: 1.1em;
          }
          
          .log {
            height: 220px;
          }
        }
        
        /* Mobile Responsive - 480px and below */
        @media (max-width: 480px) {
          body {
            padding: 10px;
          }
          
          .header {
            padding: 20px 15px;
            margin-bottom: 20px;
          }
          
          .header h1 {
            font-size: 1.8em;
            margin-bottom: 8px;
          }
          
          .header p {
            font-size: 0.95em;
          }
          
          .main-grid {
            gap: 15px;
            margin-bottom: 15px;
          }
          
          .card {
            padding: 18px;
          }
          
          .card h2 {
            font-size: 1.3em;
            margin-bottom: 15px;
          }
          
          .wifi-button {
            font-size: 1em;
            padding: 14px;
          }
          
          .status {
            font-size: 1em;
            margin-top: 12px;
          }
          
          .name-item {
            flex-direction: column;
            align-items: stretch;
            gap: 12px;
            padding: 15px;
          }
          
          .name-text {
            font-size: 1em;
            text-align: center;
            font-weight: 600;
          }
          
          .name-controls {
            justify-content: center;
            gap: 15px;
          }
          
          .management-controls {
            flex-direction: column;
            gap: 12px;
          }
          
          .ctrl-input {
            padding: 12px;
            font-size: 1em;
          }
          
          .ctrl-btn {
            padding: 12px;
            font-size: 1em;
          }
          
          .toggle-switch {
            width: 55px;
            height: 28px;
          }
          
          .toggle-slider {
            width: 24px;
            height: 24px;
          }
          
          .toggle-switch.active .toggle-slider {
            transform: translateX(27px);
          }
          
          .remove-btn {
            padding: 8px 14px;
            font-size: 0.85em;
          }
          
          .log {
            height: 200px;
            font-size: 0.8em;
            padding: 12px;
          }
          
          .progress-bar {
            margin-top: 12px;
          }
          
          .progress-text {
            font-size: 0.85em;
            margin-top: 6px;
          }
        }
        
        /* Extra small mobile - 320px and below */
        @media (max-width: 320px) {
          body {
            padding: 8px;
          }
          
          .header {
            padding: 15px 12px;
          }
          
          .header h1 {
            font-size: 1.6em;
          }
          
          .header p {
            font-size: 0.9em;
          }
          
          .card {
            padding: 15px;
          }
          
          .card h2 {
            font-size: 1.2em;
          }
          
          .wifi-button {
            font-size: 0.95em;
            padding: 12px;
          }
          
          .name-item {
            padding: 12px;
          }
          
          .name-text {
            font-size: 0.95em;
          }
          
          .ctrl-input {
            padding: 10px;
            font-size: 0.95em;
          }
          
          .ctrl-btn {
            padding: 10px;
            font-size: 0.95em;
          }
          
          .log {
            height: 180px;
            font-size: 0.75em;
            padding: 10px;
          }
          
          .status {
            font-size: 0.95em;
          }
        }
      </style>
    </head>
    <body>
      <div class="container">
        <div class="header">
          <h1>WiFi Control Panel</h1>
          <p>Network Management System</p>
        </div>
        
        <div class="main-grid">
          <div class="card">
            <h2>WiFi Control</h2>
            <button class="wifi-button" id="wifiBtn" onclick="toggleWifi()">
              <span id="btnText">Toggle WiFi</span>
            </button>
            <div class="status" id="status">Ready</div>
          </div>
          
          <div class="card">
            <h2>User Authorization</h2>
            <div id="namesContainer">
              </div>
            <div class="progress-bar">
              <div class="progress-fill" id="progressFill" style="width: 0%"></div>
            </div>
            <p class="progress-text">
              <span id="progressText">0/0 authorized</span>
            </p>
            
            <div class="management-controls">
              <input type="text" class="ctrl-input" id="newNameInput" placeholder="Enter new user name...">
              <button class="ctrl-btn" onclick="addName()">Add User</button>
            </div>
          </div>
        </div>
        
        <div class="card">
          <h2>System Log</h2>
          <div class="log" id="log">Initializing system logs...</div>
        </div>
      </div>
      
      <script>
        let wifiStatus = 'idle';
        let namesData = { names: [], toggles: {} };
        
        async function loadWifiStatus() {
          try {
            const response = await fetch('/wifi_status');
            const data = await response.json();
            wifiStatus = data.wifi_toggle_status;
            updateWifiButton();
          } catch (error) {
            console.error('Error loading WiFi status:', error);
          }
        }
        
        async function loadNamesData() {
          try {
            const response = await fetch('/names_status');
            const newNamesData = await response.json();
            namesData = newNamesData;
            renderNames();
            updateProgress();
          } catch (error) {
            console.error('Error loading names data:', error);
          }
        }
        
        function updateWifiButton() {
          const btn = document.getElementById('wifiBtn');
          const btnText = document.getElementById('btnText');
          const status = document.getElementById('status');
          
          if (wifiStatus === 'toggling') {
            btn.disabled = true;
            btnText.textContent = 'TOGGLING...';
            status.textContent = 'System is currently toggling WiFi...';
            status.className = 'status toggling';
          } else {
            btn.disabled = false;
            btnText.textContent = 'Toggle WiFi';
            status.textContent = 'Ready for activation';
            status.className = 'status';
          }
        }
        
        function renderNames() {
          const container = document.getElementById('namesContainer');
          container.innerHTML = '';
          
          namesData.names.forEach(name => {
            const nameItem = document.createElement('div');
            nameItem.className = 'name-item';
            nameItem.innerHTML = `
              <span class="name-text">${name}</span>
              <div class="name-controls">
                <div class="toggle-switch ${namesData.toggles[name] ? 'active' : ''}" onclick="toggleName('${name}')">
                  <div class="toggle-slider"></div>
                </div>
                <button class="remove-btn" onclick="removeName('${name}')">Remove</button>
              </div>
            `;
            container.appendChild(nameItem);
          });
        }
        
        function updateProgress() {
          const totalNames = namesData.names.length;
          const toggledNames = Object.values(namesData.toggles).filter(Boolean).length;
          const percentage = totalNames > 0 ? (toggledNames / totalNames) * 100 : 0;
          
          document.getElementById('progressFill').style.width = percentage + '%';
          document.getElementById('progressText').textContent = `${toggledNames}/${totalNames} authorized`;
        }
        
        async function toggleWifi() {
          if (wifiStatus === 'toggling') return;
          
          // Fetch latest status before proceeding
          await loadWifiStatus();
          if (wifiStatus === 'toggling') {
            console.log('WiFi already toggling, ignoring action');
            return;
          }
          
          const statusEl = document.getElementById('status');
          statusEl.textContent = "Initializing WiFi toggle sequence...";
          
          try {
            const response = await fetch('/toggle_wifi', { 
              method: 'POST',
              headers: {
                'Content-Type': 'application/json'
              }
            });
            
            if (!response.ok) {
              throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const text = await response.text();
            statusEl.textContent = text;
            await loadWifiStatus();
            await loadLog();
          } catch (error) {
            console.error('WiFi toggle error:', error);
            statusEl.textContent = `Error: ${error.message}`;
            await loadWifiStatus();
          }
        }
        
        async function toggleName(name) {
          try {
            // Fetch latest data before proceeding
            await loadNamesData();
            
            // Check if name still exists and get current state
            if (!namesData.names.includes(name)) {
              console.log('Name no longer exists, ignoring action');
              return;
            }
            
            const response = await fetch('/toggle_name', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ name: name })
            });
            
            if (response.ok) {
              await loadNamesData();
              await loadWifiStatus();
            } else {
              console.error('Toggle name failed:', response.status);
              await loadNamesData(); // Refresh to show current state
            }
          } catch (error) {
            console.error('Error toggling name:', error);
            await loadNamesData(); // Refresh on error
          }
        }
        
        async function addName() {
          const input = document.getElementById('newNameInput');
          const name = input.value.trim();
          
          if (!name) return;
          
          try {
            // Fetch latest data to check for conflicts
            await loadNamesData();
            
            if (namesData.names.includes(name)) {
              alert('Name already exists!');
              input.value = '';
              return;
            }
            
            const response = await fetch('/add_name', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ name: name })
            });
            
            if (response.ok) {
              input.value = '';
              await loadNamesData();
            } else {
              console.error('Add name failed:', response.status);
              await loadNamesData(); // Refresh to show current state
            }
          } catch (error) {
            console.error('Error adding name:', error);
            await loadNamesData(); // Refresh on error
          }
        }
        
        async function removeName(name) {
          try {
            // Fetch latest data before proceeding
            await loadNamesData();
            
            if (!namesData.names.includes(name)) {
              console.log('Name no longer exists, ignoring removal');
              return;
            }
            
            const response = await fetch('/remove_name', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ name: name })
            });
            
            if (response.ok) {
              await loadNamesData();
            } else {
              console.error('Remove name failed:', response.status);
              await loadNamesData(); // Refresh to show current state
            }
          } catch (error) {
            console.error('Error removing name:', error);
            await loadNamesData(); // Refresh on error
          }
        }
        
        async function loadLog() {
          try {
            const response = await fetch('/server_log');
            const text = await response.text();
            const logDiv = document.getElementById('log');
            logDiv.textContent = text;
            logDiv.scrollTop = logDiv.scrollHeight;
          } catch (error) {
            console.error('Error loading log:', error);
          }
        }
        
        // Initialize
        async function initialize() {
          await loadWifiStatus();
          await loadNamesData();
          await loadLog();
        }
        
        initialize();
        
        // Enter key support for adding names
        document.getElementById('newNameInput').addEventListener('keypress', function(e) {
          if (e.key === 'Enter') {
            addName();
          }
        });
      </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/wifi_status")
async def get_wifi_status_endpoint():
    status = read_status()
    return JSONResponse({"wifi_toggle_status": status})

@app.get("/names_status")
async def get_names_status_endpoint():
    return JSONResponse(read_names_status())

@app.post("/toggle_wifi")
async def toggle_wifi_web_endpoint(background_tasks: BackgroundTasks):
    try:
        current_status = read_status()
        if current_status == "toggling":
            return PlainTextResponse("WiFi is already being toggled. Please wait.", status_code=409)

        background_tasks.add_task(handle_wifi_background_task) # Execute toggle_wifi in a background thread
        
        # After starting the background task, the status will eventually change to "idle"
        # The frontend will poll for this change.
        return PlainTextResponse("WiFi neural network reconfiguration initiated.")
    except Exception as e:
        write_status("idle") # Ensure status is reset even on immediate error
        return PlainTextResponse(f"Error initiating WiFi toggle: {str(e)}", status_code=500)

@app.post("/toggle_name")
async def toggle_name_endpoint(name_toggle: NameToggle, background_tasks: BackgroundTasks):
    try:
        data = read_names_status()
        name = name_toggle.name
        
        if name in data["toggles"]:
            data["toggles"][name] = not data["toggles"][name]
            write_names_status(data)
            
            all_toggled = all(data["toggles"].values()) and len(data["names"]) > 0
            
            if all_toggled:
                # Reset all toggles and trigger WiFi toggle
                for n in data["names"]:
                    data["toggles"][n] = False
                write_names_status(data)
                
                # Trigger WiFi toggle in background
                current_wifi_status = read_status()
                if current_wifi_status != "toggling":
                    background_tasks.add_task(handle_wifi_background_task)
                else:
                    print("WiFi already toggling due to all names being authorized. Skipping another toggle.")
            
            return JSONResponse({"success": True, "all_toggled": all_toggled})
        
        return JSONResponse({"success": False, "error": "Name not found"})
    except Exception as e:
        print(f"Error in toggle_name_endpoint: {e}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.post("/add_name")
async def add_name_endpoint(add_name: AddName):
    data = read_names_status()
    name = add_name.name.strip()
    
    if name and name not in data["names"]:
        data["names"].append(name)
        data["toggles"][name] = False
        write_names_status(data)
        return JSONResponse({"success": True})
    
    return JSONResponse({"success": False, "error": "Name already exists or invalid"})

@app.post("/remove_name")
async def remove_name_endpoint(remove_name: RemoveName):
    data = read_names_status()
    name = remove_name.name
    
    if name in data["names"]:
        data["names"].remove(name)
        if name in data["toggles"]: # Ensure the toggle state is also removed
            del data["toggles"][name]
        write_names_status(data)
        return JSONResponse({"success": True})
    
    return JSONResponse({"success": False, "error": "Name not found"})

@app.get("/server_log")
async def server_log():
    log_file = "server.log" # Assuming a log file named server.log
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            content = f.read()
    else:
        content = "No log file found."
    return PlainTextResponse(content)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8765)
