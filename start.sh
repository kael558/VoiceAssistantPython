#!/bin/bash

nohup ngrok http --domain=robust-classic-trout.ngrok-free.app 8765 > ngrok.log 2>&1 &

sleep 5

python ~/Desktop/VoiceAssistantPython/server.py > server.log 2>&1 &
