import json
import os

import websockets
from dotenv import load_dotenv


# Load environment variables from the project's .env file.
load_dotenv()


# Read the OpenAI API key from the environment.
#
# The actual secret is stored in .env and is intentionally excluded
# from Git. This variable only contains the key while the application
# is running.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


# Lower-cost Realtime model selected for the SMB receptionist.
#
# This keeps the project aligned with the goal of minimizing
# operating cost while still supporting real-time voice interactions.
OPENAI_MODEL = "gpt-realtime-2.1-mini"

OPENAI_REALTIME_URL = (
    "wss://api.openai.com/v1/realtime"
    f"?model={OPENAI_MODEL}"
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


async def configure_realtime_session(openai_websocket):
    """
    Configure the OpenAI Realtime session for a telephone receptionist.

    This controls:
    - The model
    - Audio input/output
    - Voice selection
    - Turn detection
    - Basic receptionist behavior

    Twilio Media Streams use G.711 μ-law telephone audio.
    We configure OpenAI to use the matching PCMU format so we can
    eventually pass audio between Twilio and OpenAI without doing
    audio transcoding inside Python.
    """

    session_update = {
        "type": "session.update",
        "session": {
            "type": "realtime",

            # Model used for this Realtime session.
            "model": OPENAI_MODEL,

            # The receptionist should respond with spoken audio.
            "output_modalities": ["audio"],

            "audio": {
                "input": {
                    # G.711 μ-law / PCMU matches Twilio's telephone
                    # Media Stream audio format.
                    "format": {
                        "type": "audio/pcmu",
                    },

                    # Voice activity detection determines when the
                    # caller has finished speaking and when the model
                    # should begin generating a response.
                    "turn_detection": {
                        "type": "semantic_vad",
                        "eagerness": "auto",
                        "create_response": True,
                        "interrupt_response": True,
                    },
                },

                "output": {
                    # Generate PCMU audio so the response can later
                    # be sent directly back to Twilio.
                    "format": {
                        "type": "audio/pcmu",
                    },

                    # Voice used by the AI receptionist.
                    "voice": "marin",
                },
            },

            # Initial system behavior.
            #
            # We intentionally keep this simple for now. Business
            # information, tools, transfer behavior, and scheduling
            # logic will be added after the audio pipeline works.
            "instructions": (
                "You are an AI receptionist for a small business. "
                "Be professional, friendly, concise, and conversational. "
                "Speak naturally as if answering a business telephone. "
                "Ask one question at a time. "
                "Do not invent business information you have not been given."
            ),
        },
    }

    # Send the session configuration over the existing OpenAI
    # Realtime WebSocket connection.
    await openai_websocket.send(
        json.dumps(session_update)
    )

    print("OpenAI Realtime session configuration sent.")