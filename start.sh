#!/bin/bash

sleep 10

nohup /usr/local/bin/ngrok http --domain=robust-classic-trout.ngrok-free.app 8765 > ~/Desktop/VoiceAssistantPython/ngrok.log 2>&1 &
NGROK_PID=$!
echo "ngrok started with PID $NGROK_PID"

sleep 5

source ~/Desktop/VoiceAssistantPython/venv/bin/activate
python ~/Desktop/VoiceAssistantPython/server.py > ~/Desktop/VoiceAssistantPython/server.log 2>&1 &
python ~/Desktop/VoiceAssistantPython/web_server.py > ~/Desktop/VoiceAssistantPython/webserver.log 2>&1 & 
