# Standard library imports used to read environment variables
# and decode incoming JSON messages from Twilio.
import os
import json

# FastAPI provides the web application, HTTP responses,
# and WebSocket support.
from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect

# python-dotenv loads variables from a local .env file.
from dotenv import load_dotenv

# Twilio's VoiceResponse class generates TwiML.
from twilio.twiml.voice_response import VoiceResponse


# Load environment variables from the project's .env file, if one exists.
load_dotenv()


# PUBLIC_URL will eventually be the public HTTPS address that Twilio can reach.
#
# During local development, FastAPI runs on localhost, but Twilio cannot
# connect directly to localhost on our computer. Later we will expose the
# application through a secure public tunnel.
PUBLIC_URL = os.getenv("PUBLIC_URL")


# Create the FastAPI application.
# Uvicorn loads this object when we run:
#
# uvicorn app.main:app --reload
app = FastAPI(title="AI SMB Receptionist")


# Basic health-check endpoint.
#
# This gives us a quick way to confirm that the Python application is running
# before involving Twilio, WebSockets, or OpenAI.
@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "AI SMB Receptionist",
    }


# Twilio will send an HTTP POST request to this endpoint whenever someone
# calls our Twilio phone number.
#
# The purpose of this endpoint is NOT to handle the call audio itself.
# Instead, it returns TwiML instructions telling Twilio where the live audio
# stream should be sent.
@app.post("/incoming-call")
async def incoming_call():
    # Make sure we have a public address configured before attempting
    # to build the WebSocket URL.
    if not PUBLIC_URL:
        return Response(
            content="PUBLIC_URL is not configured.",
            status_code=500,
            media_type="text/plain",
        )

    # Create a new TwiML <Response> document.
    response = VoiceResponse()

    # <Connect><Stream> creates a bidirectional Twilio Media Stream.
    #
    # Twilio will open a WebSocket connection to our /media-stream endpoint.
    # Caller audio will travel:
    #
    # Caller -> Twilio -> WebSocket -> Python
    #
    # Later, generated AI audio will travel in the opposite direction:
    #
    # Python -> WebSocket -> Twilio -> Caller
    connect = response.connect()

    # Twilio Media Streams require a secure WebSocket URL using wss://.
    #
    # Our public tunnel will use https:// for normal HTTP requests.
    # Here we convert that address to wss:// for the WebSocket connection.
    websocket_url = PUBLIC_URL.replace("https://", "wss://") + "/media-stream"

    connect.stream(url=websocket_url)

    # Return the generated TwiML as XML.
    #
    # Twilio reads this XML and executes the <Connect><Stream> instruction.
    return Response(
        content=str(response),
        media_type="application/xml",
    )



@app.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    """
    Receive a real-time Twilio Media Stream.

    Twilio opens this WebSocket after receiving the <Connect><Stream>
    instruction from the /incoming-call endpoint.

    Unlike a normal HTTP request, this connection remains open for
    the duration of the call.

    Twilio sends JSON events such as:

        connected
        start
        media
        stop

    The "media" events contain the caller's live audio.
    """

    # Accept the incoming WebSocket connection.
    # FastAPI requires this before messages can be received or sent.
    await websocket.accept()

    print("Twilio Media Stream connected.")

    try:
        # Keep listening for messages until Twilio closes the stream.
        while True:
            # Twilio sends each WebSocket message as JSON-formatted text.
            message = await websocket.receive_text()

            # Convert the JSON string into a Python dictionary.
            data = json.loads(message)

            # Twilio identifies the type of message in the "event" field.
            event_type = data.get("event")

            if event_type == "connected":
                print("Twilio WebSocket protocol connected.")

            elif event_type == "start":
                # The start event contains identifiers for this
                # specific call and Media Stream.
                start_data = data.get("start", {})

                stream_sid = start_data.get("streamSid")
                call_sid = start_data.get("callSid")

                print(f"Media Stream started: {stream_sid}")
                print(f"Twilio Call SID: {call_sid}")

            elif event_type == "media":
                # Caller audio is arriving here.
                #
                # We are intentionally ignoring the audio payload for now.
                # In the next phase, this audio will be forwarded to
                # the OpenAI Realtime API.
                pass

            elif event_type == "stop":
                # Twilio sends this when the Media Stream ends normally.
                print("Twilio Media Stream stopped.")
                break

    except WebSocketDisconnect:
        # This commonly happens when the caller hangs up or Twilio
        # closes the connection.
        print("Twilio Media Stream disconnected.")