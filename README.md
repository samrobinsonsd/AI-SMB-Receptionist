# AI SMB Receptionist

A low-cost, real-time AI voice receptionist for small and medium-sized businesses, built with Python, Twilio Voice, and the OpenAI Realtime API.

## Project Goal

Build a functional AI receptionist capable of answering incoming PSTN calls, conducting natural real-time voice conversations, handling common business inquiries, collecting caller information, and eventually performing actions such as call transfers and appointment requests.

The project is being designed around a target operating cost of **$5 or less per day** for a small-business deployment.

## Architecture

Initial call flow:

```text
Incoming PSTN Call
        ↓
Twilio Voice
        ↓
Twilio Media Stream
        ↓
Python / FastAPI
        ↓
OpenAI Realtime API
        ↓
Python / FastAPI
        ↓
Twilio Media Stream
        ↓
Caller
```

The Python application acts as the real-time orchestration layer between Twilio and OpenAI.

## Technology

* Python
* FastAPI
* asyncio
* WebSockets
* Twilio Programmable Voice
* Twilio Media Streams
* OpenAI Realtime API

## Initial MVP

The first version will focus on the core receptionist workflow:

1. Answer an incoming business call.
2. Establish a bidirectional audio stream.
3. Connect the call to OpenAI Realtime.
4. Conduct a natural voice conversation.
5. Identify the caller's intent.
6. Answer basic business questions.
7. Collect caller information and messages.
8. End or transfer the call appropriately.

## Development Phases

### Phase 1: Twilio → Python

Establish an incoming Twilio call and stream call audio to a Python WebSocket endpoint.

### Phase 2: Python → OpenAI Realtime

Forward incoming caller audio to the OpenAI Realtime API and verify real-time speech processing.

### Phase 3: OpenAI → Python → Twilio

Stream generated audio responses back through Twilio to the caller, completing the real-time conversational loop.

### Phase 4: Receptionist Functions

Add business-specific functionality such as:

* Business information and hours
* Caller intent detection
* Message taking
* Call transfers
* Appointment requests
* SMS confirmations
* Call summaries
* Error and fallback handling

### Phase 5: Cost and Production Optimization

Track and optimize:

* Call duration
* Twilio usage
* OpenAI audio usage
* Cost per call
* Cost per minute
* Daily operating cost

## Cost Target

The system is being developed around an operating-cost target of:

**≤ $5/day**

Usage and cost telemetry will be incorporated into the application so the target can be measured against real call traffic rather than estimated theoretically.

## Status

**In development**

Current milestone: Phase 1, establishing Twilio Voice → Python WebSocket audio streaming.
