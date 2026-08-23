import os

from dotenv import load_dotenv
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse


# Load Twilio API credentials and transfer configuration
# from the local .env file.
load_dotenv()

# The Account SID identifies the Twilio account that owns
# the active call we want to control.
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")

# API Key SID and Secret authenticate this application
# to Twilio's REST API.
#
# Using a dedicated API key is preferable to embedding the
# account's primary Auth Token in the application.
TWILIO_API_KEY = os.getenv("TWILIO_API_KEY")
TWILIO_API_SECRET = os.getenv("TWILIO_API_SECRET")

# Destination used when the AI receptionist transfers a
# caller to a human staff member.
STAFF_TRANSFER_NUMBER = os.getenv("STAFF_TRANSFER_NUMBER")


def get_twilio_client():
    """
    Create an authenticated Twilio REST API client.

    Twilio API key authentication uses:

        API Key SID     -> username
        API Key Secret  -> password
        Account SID     -> target account

    Keeping this in one helper makes it easy to reuse the
    authenticated client for future Twilio functionality.
    """

    if not TWILIO_ACCOUNT_SID:
        raise RuntimeError(
            "TWILIO_ACCOUNT_SID is not configured."
        )

    if not TWILIO_API_KEY:
        raise RuntimeError(
            "TWILIO_API_KEY is not configured."
        )

    if not TWILIO_API_SECRET:
        raise RuntimeError(
            "TWILIO_API_SECRET is not configured."
        )

    return Client(
        TWILIO_API_KEY,
        TWILIO_API_SECRET,
        TWILIO_ACCOUNT_SID,
    )


def transfer_call_to_staff(call_sid):
    """
    Transfer an active Twilio call from the AI receptionist
    to the configured staff telephone number.

    The caller is currently connected to our AI through
    <Connect><Stream>. Updating the active Twilio Call with
    new TwiML replaces that stream with a normal <Dial>.
    """

    if not STAFF_TRANSFER_NUMBER:
        raise RuntimeError(
            "STAFF_TRANSFER_NUMBER is not configured."
        )

    # Create an authenticated Twilio REST client using
    # the application's dedicated API key.
    client = get_twilio_client()

    # Build replacement instructions for the active call.
    response = VoiceResponse()


    response.dial(
        STAFF_TRANSFER_NUMBER,
        timeout=20,
    )

    # Replace the current AI Media Stream with the new
    # transfer instructions.
    client.calls(call_sid).update(
        twiml=str(response)
    )

    print(
        f"Transferred Twilio call {call_sid} "
        f"to {STAFF_TRANSFER_NUMBER}."
    )

    return True