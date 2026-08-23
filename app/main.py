import asyncio
import json
import os

import websockets
from dotenv import load_dotenv
from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect
from twilio.twiml.voice_response import VoiceResponse

from app.openai_realtime import (
    connect_to_openai,
    configure_realtime_session,
    start_receptionist_greeting,
)


# Load environment variables from .env.
load_dotenv()


# Public HTTPS address used by Twilio to reach this application.
#
# Example:
# https://random-name.trycloudflare.com
#
# We keep this in main.py because it is part of the Twilio/FastAPI
# configuration, not the OpenAI connection configuration.
PUBLIC_URL = os.getenv("PUBLIC_URL")


# FastAPI handles:
# 1. Twilio's HTTP webhook for incoming calls.
# 2. Twilio's WebSocket connection for live Media Streams.
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
    
    # Twilio assigns a unique Stream SID to each Media Stream.
    # We need this identifier when sending generated audio back to Twilio.
    stream_sid = None

    print("Twilio Media Stream connected.")
    
    # Establish a second WebSocket connection from our Python server
    # to OpenAI Realtime.
    #
    # At this point the application has two independent persistent
    # connections:
    #
    # Twilio <-> Python <-> OpenAI
    openai_websocket = await connect_to_openai()
    
    # Configure the newly created Realtime session before
    # caller audio begins flowing to OpenAI.
    await configure_realtime_session(openai_websocket)
    
    # OpenAI sends events over the WebSocket as JSON messages.
    #
    # This background task listens for those events while the main
    # function continues listening to Twilio.
    async def receive_openai_events():
        try:
            async for message in openai_websocket:
                data = json.loads(message)
                event_type = data.get("type")

                # OpenAI sends generated speech in small base64-encoded audio chunks.
                # Since the session output format is PCMU, the audio can be forwarded
                # directly to Twilio without transcoding.
                if event_type == "response.output_audio.delta":
                    audio_delta = data.get("delta")

                    # Twilio requires the Stream SID so it knows which active
                    # phone call should receive this audio.
                    if audio_delta and stream_sid:
                        twilio_audio_event = {
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {
                                "payload": audio_delta,
                            },
                        }

                        # Send the generated audio back over the existing Twilio
                        # WebSocket connection.
                        await websocket.send_text(
                            json.dumps(twilio_audio_event)
                        )

                # Avoid logging every tiny audio and transcript chunk.
                # These events arrive many times per second.
                noisy_events = {
                    "response.output_audio.delta",
                    "response.output_audio_transcript.delta",
                }

                if event_type not in noisy_events:
                    print(f"OpenAI event: {event_type}")

        except websockets.ConnectionClosed:
            print("OpenAI Realtime connection closed.")

        except Exception as exc:
            # Background asyncio tasks can otherwise fail quietly,
            # so print unexpected listener errors for debugging.
            print(
                f"OpenAI listener error: "
                f"{type(exc).__name__}: {exc}"
            )
    
    # asyncio.create_task() starts the OpenAI listener without blocking
    # the Twilio receive loop below.
    openai_listener = asyncio.create_task(
        receive_openai_events()
    )

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
                
                # The Twilio Media Stream is now fully established and we have
                # its Stream SID. It is safe for OpenAI to generate audio because
                # we now know where to send that audio.
                await start_receptionist_greeting(openai_websocket)

            elif event_type == "media":
                # Twilio sends the caller's audio inside media.payload.
                #
                # The payload is already:
                # - G.711 μ-law / PCMU
                # - 8 kHz
                # - base64 encoded
                #
                # OpenAI Realtime is configured to accept the same PCMU
                # format, so we can forward the payload directly without
                # decoding or transcoding the audio in Python.
                media_data = data.get("media", {})
                audio_payload = media_data.get("payload")

                if audio_payload:
                    # OpenAI's input_audio_buffer.append event adds this
                    # chunk of caller audio to the active Realtime session.
                    openai_audio_event = {
                        "type": "input_audio_buffer.append",
                        "audio": audio_payload,
                    }

                    # Send the caller's audio chunk to OpenAI.
                    await openai_websocket.send(
                        json.dumps(openai_audio_event)
                    )

            elif event_type == "stop":
                # Twilio sends this when the Media Stream ends normally.
                print("Twilio Media Stream stopped.")
                break

    except WebSocketDisconnect:
        # This commonly happens when the caller hangs up or Twilio
        # closes the connection.
        print("Twilio Media Stream disconnected.")

    finally:
        # Stop the background OpenAI listener when the Twilio call ends.
        openai_listener.cancel()

        # Close the OpenAI WebSocket if it is still open.
        await openai_websocket.close()

        print("OpenAI Realtime connection closed.")