import json
import os

import websockets
from dotenv import load_dotenv

from app.business_config import BUSINESS_CONFIG


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


def build_business_context():
    """
    Convert the business configuration into concise information that
    can be provided to the AI receptionist.

    Only relatively static business facts belong here. Dynamic data
    such as inventory and pricing will eventually come from tools.
    """

    hours = "\n".join(
        f"{day.capitalize()}: {hours}"
        for day, hours in BUSINESS_CONFIG["hours"].items()
    )

    specialties = ", ".join(
        BUSINESS_CONFIG["specialties"]
    )
    
    knowledge = BUSINESS_CONFIG.get(
    "knowledge",
    {},
    )

    services = ", ".join(
        knowledge.get("services", [])
    )

    livestock = ", ".join(
        knowledge.get("livestock", [])
    )

    livestock_practices = ", ".join(
        knowledge.get("livestock_practices", [])
    )

    products = ", ".join(
        knowledge.get("products", [])
    )

    return (
        f"Business name: {BUSINESS_CONFIG['name']}\n"
        f"Business description: {BUSINESS_CONFIG['description']}\n"
        f"Address: {BUSINESS_CONFIG['address']}\n"
        f"Phone: {BUSINESS_CONFIG['phone']}\n"
        f"Specialties: {specialties}\n"
        f"Services: {services}\n"
        f"Livestock sold: {livestock}\n"
        f"Livestock practices: {livestock_practices}\n"
        f"Products sold: {products}\n"
        f"Store hours:\n{hours}"
    )
    

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
    
    
    # Build the static business knowledge supplied to the receptionist.
    business_context = build_business_context()
    

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
                f"You are the AI receptionist for {BUSINESS_CONFIG['name']}.\n\n"
                f"BUSINESS INFORMATION:\n{business_context}\n\n"

                "RECEPTIONIST RULES:\n"
                "- Be friendly, concise, and conversational.\n"
                "- Speak naturally as if answering a business telephone.\n"
                "- Ask one question at a time.\n"
                "- Use the business information above when answering questions.\n"
                "- Never invent inventory, pricing, availability, policies, "
                "or other business information you have not been given.\n"
                "- If information is unavailable, say that you do not have "
                "access to that information.\n"
                "- When appropriate, offer to take a message, arrange a callback, "
                "or connect the caller with staff."
                "- If the caller needs staff follow-up, offer to take a message.\n"
                "- Before taking a message, collect the caller's name, callback "
                "number, and reason for calling.\n"
                "- Confirm important details before submitting the message.\n"
                "- Use the take_message tool only after you have enough information."
                "- If the caller explicitly asks to speak with a person, offer a live transfer.\n"
                "- Use transfer_to_staff only after confirming the caller wants to be transferred.\n"
                "- Do not claim the transfer succeeded until the transfer tool has been executed.\n"
                "- Before using transfer_to_staff, tell the caller you are connecting them "
                "with a member of the team.\n"
                "- After saying that, immediately use transfer_to_staff.\n"
                "- Do not continue speaking after requesting the transfer.\n"
                "- Answer questions about products and services using the provided business information.\n"
                "- General product categories may be confirmed, but never claim a specific item is currently in stock unless live inventory is available.\n"
                "- You may state that all fish are quarantined prior to sale.\n"
            ),
            
            "tools": [
                {
                    "type": "function",
                    "name": "take_message",
                    "description": (
                        "Capture a message for Reefwise staff when a caller "
                        "needs a callback or follow-up."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Caller's name.",
                            },
                            "phone": {
                                "type": "string",
                                "description": "Caller's callback phone number.",
                            },
                            "reason": {
                                "type": "string",
                                "description": "Primary reason for the call.",
                            },
                            "notes": {
                                "type": "string",
                                "description": (
                                    "Any additional useful details for staff."
                                ),
                            },
                            "callback_requested": {
                                "type": "boolean",
                                "description": (
                                    "Whether the caller explicitly wants "
                                    "a callback."
                                ),
                            },
                        },
                        "required": [
                            "name",
                            "phone",
                            "reason",
                            "callback_requested",
                        ],
                    },
                },
                {
                    "type": "function",
                    "name": "transfer_to_staff",
                    "description": (
                        "Transfer the active caller to a Reefwise staff member "
                        "when the caller asks to speak with someone or when live "
                        "staff assistance is appropriate."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reason": {
                                "type": "string",
                                "description": (
                                    "Brief reason why the caller is being transferred."
                                ),
                            },
                        },
                        "required": [
                            "reason",
                        ],
                    },
                },
            ],
        },
    }

    # Send the session configuration over the existing OpenAI
    # Realtime WebSocket connection.
    await openai_websocket.send(
        json.dumps(session_update)
    )

    print("OpenAI Realtime session configuration sent.")
    

async def start_receptionist_greeting(openai_websocket):
    """
    Ask OpenAI to generate the first response of the call.

    Without this event, the Realtime session waits for caller speech
    before generating a response. A receptionist should answer first,
    so we explicitly request an opening greeting.
    """

    greeting_event = {
        "type": "response.create",
        "response": {
            "instructions": (
                "Greet the caller as a professional receptionist. "
                "Say: Thank you for calling Reefwise, your aquatic solution provider. "
                "How can I help you today?"
            ),
        },
    }

    await openai_websocket.send(
        json.dumps(greeting_event)
    )

    print("Receptionist greeting requested.")