from pipecat.services.azure import AzureTTSService
from dotenv import load_dotenv
import os
load_dotenv(override=True)

tts = AzureTTSService(
            api_key=os.getenv("AZURE_SPEECH_API_KEY"),
            region=os.getenv("AZURE_REGION"),
        )
