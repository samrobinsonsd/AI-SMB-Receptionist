import asyncio
import json
import os

import websockets
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pathlib import Path
from twilio.twiml.voice_response import VoiceResponse

from datetime import datetime
from zoneinfo import ZoneInfo

from app.openai_realtime import (
    connect_to_openai,
    configure_realtime_session,
    start_receptionist_greeting,
)

from app.database import (
    add_call_usage,
    end_call,
    get_calls,
    get_messages,
    initialize_database,
    save_message,
    start_call,
    update_message_status,
)

from app.call_control import transfer_call_to_staff

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


# Make sure the local SQLite database and required tables exist
# whenever the FastAPI application starts.
initialize_database()


# Path to the HTML inbox template.
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


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


@app.get("/messages")
async def list_messages():
    """
    Return all receptionist messages stored in SQLite.

    This is a simple development endpoint for verifying that caller
    messages are being persisted correctly.

    Authentication will be added before this is treated as a
    production-facing administrative endpoint.
    """

    messages = get_messages()

    return {
        "count": len(messages),
        "messages": messages,
    }


@app.get("/calls")
async def list_calls():
    """
    Return basic call telemetry.

    This development endpoint lets us verify that calls are
    being persisted with timestamps and durations.
    """

    calls = get_calls()

    return {
        "count": len(calls),
        "calls": calls,
    }


@app.get("/stats")
async def get_stats():
    """
    Return high-level receptionist usage and cost statistics.

    Calls without OpenAI usage data are excluded from cost averages
    because they were recorded before AI usage tracking was enabled.
    """

    calls = get_calls()

    # Calls that contain OpenAI usage telemetry.
    measured_calls = [
        call for call in calls
        if (
            call["input_tokens"] > 0
            or call["output_tokens"] > 0
        )
    ]

    total_seconds = sum(
        call["duration_seconds"] or 0
        for call in measured_calls
    )

    total_cost = sum(
        call["estimated_total_cost_usd"]
        for call in measured_calls
    )

    call_count = len(measured_calls)

    average_cost = (
        total_cost / call_count
        if call_count
        else 0
    )

    average_duration = (
        total_seconds / call_count
        if call_count
        else 0
    )

    return {
        "calls": call_count,
        "minutes": round(
            total_seconds / 60,
            1,
        ),
        "total_cost_usd": round(
            total_cost,
            4,
        ),
        "average_cost_usd": round(
            average_cost,
            4,
        ),
        "average_duration_seconds": round(
            average_duration,
        ),
        "daily_budget_usd": 5.00,
    }


@app.get("/inbox", response_class=HTMLResponse)
async def inbox():
    """
    Serve the simple receptionist message inbox.

    The page loads caller messages from the /messages API and uses
    the existing PATCH endpoint to update message status.
    """

    inbox_path = TEMPLATES_DIR / "inbox.html"

    return inbox_path.read_text(
        encoding="utf-8"
    )

@app.patch("/messages/{message_id}/status")
async def change_message_status(
    message_id: int,
    status: str,
):
    """
    Change the workflow status of a caller message.

    Example:

    PATCH /messages/1/status?status=contacted

    Valid statuses:
    - new
    - contacted
    - closed
    """

    try:
        updated = update_message_status(
            message_id=message_id,
            status=status,
        )

    except ValueError as exc:
        # Return HTTP 400 when an unsupported status is requested.
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    if not updated:
        # Return HTTP 404 if the requested message does not exist.
        raise HTTPException(
            status_code=404,
            detail="Message not found.",
        )

    return {
        "success": True,
        "message_id": message_id,
        "status": status,
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


async def handle_take_message(arguments):
    """
    Store a structured caller message in SQLite.

    OpenAI provides the message details as structured function-call
    arguments. Python is responsible for performing the actual business
    action, which in this case is persisting the message.
    """

    name = arguments.get("name")
    phone = arguments.get("phone")
    reason = arguments.get("reason")
    notes = arguments.get("notes", "")
    callback_requested = arguments.get(
        "callback_requested",
        False,
    )

    # Store the message permanently in SQLite.
    message_id = save_message(
        name=name,
        phone=phone,
        reason=reason,
        notes=notes,
        callback_requested=callback_requested,
    )

    # Keep the console output for development and debugging.
    print("\n--- NEW REEFWISE MESSAGE ---")
    print(f"Message ID: {message_id}")
    print(f"Name: {name}")
    print(f"Phone: {phone}")
    print(f"Reason: {reason}")
    print(f"Notes: {notes}")
    print(f"Callback requested: {callback_requested}")
    print("----------------------------\n")

    return message_id

    
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
    
    # Twilio identifiers for the currently active call.
    #
    # stream_sid identifies the Media Stream.
    # call_sid identifies the actual Twilio phone call.
    stream_sid = None
    call_sid = None
    
    # Tracks the primary business outcome of this call.
    #
    # The default means the AI handled the conversation without
    # creating a message or transferring the caller.
    call_outcome = "completed"

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
        
        nonlocal call_outcome
        
        try:
            async for message in openai_websocket:
                data = json.loads(message)
                event_type = data.get("type")
                
                # Every completed OpenAI response includes usage data.
                #
                # A phone call usually contains multiple responses, so
                # each response's usage is added to the current call.
                if event_type == "response.done" and call_sid:
                    response_data = data.get("response", {})
                    usage = response_data.get("usage") or {}

                    input_details = (
                        usage.get("input_token_details")
                        or usage.get("input_tokens_details")
                        or {}
                    )

                    output_details = (
                        usage.get("output_token_details")
                        or usage.get("output_tokens_details")
                        or {}
                    )

                    input_tokens = usage.get(
                        "input_tokens",
                        0,
                    )

                    output_tokens = usage.get(
                        "output_tokens",
                        0,
                    )

                    input_audio_tokens = input_details.get(
                        "audio_tokens",
                        0,
                    )

                    output_audio_tokens = output_details.get(
                        "audio_tokens",
                        0,
                    )
                    
                    cached_input_tokens = input_details.get(
                    "cached_tokens",
                        0,
                    )
                    
                    # Cached input may contain both text and audio tokens.
                    # Realtime prices cached audio differently from cached text,
                    # so capture the detailed breakdown when OpenAI provides it.
                    cached_details = (
                    input_details.get("cached_tokens_details")
                    or {}
                    )

                    cached_text_input_tokens = cached_details.get(
                    "text_tokens",
                        0,
                    )

                    cached_audio_input_tokens = cached_details.get(
                        "audio_tokens",
                        0,
                    )
                    
                    add_call_usage(
                        call_sid=call_sid,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        input_audio_tokens=input_audio_tokens,
                        output_audio_tokens=output_audio_tokens,
                        cached_input_tokens=cached_input_tokens,
                        cached_text_input_tokens=cached_text_input_tokens,
                        cached_audio_input_tokens=cached_audio_input_tokens,
                    )

                    print(
                        "OpenAI usage: "
                        f"{input_tokens} input tokens, "
                        f"{output_tokens} output tokens, "
                        f"{input_audio_tokens} input audio tokens, "
                        f"{output_audio_tokens} output audio tokens."
                        f"{cached_input_tokens} cached input tokens."
                        f"{cached_text_input_tokens} cached text tokens, "
                        f"{cached_audio_input_tokens} cached audio tokens."
                    )                
                
                # OpenAI emits this event when a function/tool call has
                # finished and all arguments have been generated.
                if event_type == "response.function_call_arguments.done":
                    tool_name = data.get("name")
                    call_id = data.get("call_id")
                    arguments_json = data.get("arguments", "{}")

                    # Convert the tool arguments from JSON text into
                    # a normal Python dictionary.
                    arguments = json.loads(arguments_json)

                    if tool_name == "take_message":
                        await handle_take_message(arguments)
                        
                        # This call resulted in a structured message for staff.
                        call_outcome = "message"

                        # Tell OpenAI that Python successfully executed
                        # the requested tool.
                        tool_result = {
                            "type": "conversation.item.create",
                            "item": {
                                "type": "function_call_output",
                                "call_id": call_id,
                                "output": json.dumps(
                                    {
                                        "success": True,
                                        "message": (
                                            "The message was captured "
                                            "for Reefwise staff."
                                        ),
                                    }
                                ),
                            },
                        }

                        await openai_websocket.send(
                            json.dumps(tool_result)
                        )

                        # After a tool finishes, explicitly ask OpenAI
                        # to continue the conversation and tell the
                        # caller the result.
                        await openai_websocket.send(
                            json.dumps(
                                {
                                    "type": "response.create",
                                }
                            )
                        )

                    elif tool_name == "transfer_to_staff":
                        # The AI has confirmed that the caller wants live staff
                        # assistance and has requested a transfer.
                        reason = arguments.get(
                            "reason",
                            "No transfer reason provided.",
                        )
                        
                        # The AI receptionist handed the active call to staff.
                        call_outcome = "transferred"

                        print("\n--- LIVE CALL TRANSFER ---")
                        print(f"Call SID: {call_sid}")
                        print(f"Reason: {reason}")
                        print("--------------------------\n")

                        if not call_sid:
                            raise RuntimeError(
                                "Cannot transfer call because Call SID is unavailable."
                            )

                        # Updating the active Twilio call replaces the current
                        # <Connect><Stream> AI session with <Dial> instructions.
                        transfer_call_to_staff(call_sid)

                        # We intentionally do not send response.create here.
                        #
                        # Twilio is taking control of the call and leaving the
                        # AI Media Stream, so the normal Realtime conversation
                        # should not continue after this point.

                # If the caller starts speaking while AI audio is still being played,
                # clear Twilio's outbound media buffer so the receptionist stops
                # talking immediately.
                if event_type == "input_audio_buffer.speech_started":
                    if stream_sid:
                        clear_event = {
                            "event": "clear",
                            "streamSid": stream_sid,
                        }

                        await websocket.send_text(
                            json.dumps(clear_event)
                        )

                        print("Caller interruption detected. Cleared Twilio audio buffer.")

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
                
                # Persist the call as soon as Twilio provides its identifiers.
                # This starts our usage and cost-tracking record.
                start_call(
                    call_sid=call_sid,
                    stream_sid=stream_sid,
                )
                
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
                
                # Complete the usage record for this call.
                if call_sid:
                    end_call(
                        call_sid=call_sid,
                        outcome=call_outcome,
                    )
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