import os

import websockets
from dotenv import load_dotenv


# Load the API key from the local .env file.
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

OPENAI_REALTIME_URL = (
    "wss://api.openai.com/v1/realtime"
    "?model=gpt-realtime"
)


async def connect_to_openai():
    """
    Open a persistent WebSocket connection to OpenAI Realtime.

    This connection is created once per active Twilio call and remains
    open while the caller is speaking with the AI receptionist.
    """

    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    openai_websocket = await websockets.connect(
        OPENAI_REALTIME_URL,
        additional_headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
        },
    )

    print("Connected to OpenAI Realtime.")

    return openai_websocket