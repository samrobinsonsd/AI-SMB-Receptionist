# AI SMB Receptionist

A low-cost, real-time AI voice receptionist for small and medium-sized businesses, built with Python, Twilio Voice, and the OpenAI Realtime API.

The project started with a simple question:

**Can a small business deploy a genuinely useful AI receptionist for less than $5 per day?**

So far, the answer looks promising.

The receptionist can answer real PSTN calls, conduct natural bidirectional voice conversations, answer business-specific questions, take structured messages, transfer callers to a human, handle caller interruptions, and track call usage and estimated operating cost.

The project is open source and intended to be adapted to other businesses.

---

## Features

- Real PSTN phone number through Twilio Voice
- Bidirectional real-time audio using Twilio Media Streams
- OpenAI Realtime voice conversations
- Caller interruption / barge-in handling
- Configurable business information and knowledge
- Guardrails for information the AI should not guess
- Structured caller message capture
- Live call transfer to a human
- SQLite persistence
- Caller message workflow
- Call history and outcomes
- OpenAI token and audio usage tracking
- Cached-token tracking
- Estimated OpenAI cost per call
- Estimated Twilio cost per call
- Daily usage and cost dashboard
- Configurable daily cost target

---

## Architecture

```text
                         ┌─────────────────────┐
                         │       Caller        │
                         └──────────┬──────────┘
                                    │
                                    │ PSTN
                                    ▼
                         ┌─────────────────────┐
                         │    Twilio Voice     │
                         │   Media Streams     │
                         └──────────┬──────────┘
                                    │
                                    │ WebSocket
                                    │ G.711 μ-law
                                    ▼
                         ┌─────────────────────┐
                         │       FastAPI       │
                         │   Python / asyncio  │
                         └──────────┬──────────┘
                                    │
                       WebSocket    │
                                    ▼
                         ┌─────────────────────┐
                         │  OpenAI Realtime    │
                         │       API           │
                         └─────────────────────┘

                                  FastAPI
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
             ┌─────────────┐                 ┌─────────────┐
             │   SQLite    │                 │  Dashboard  │
             │ Calls / Msg │                 │ Usage / Msg │
             └─────────────┘                 └─────────────┘
```

When a call arrives, Twilio requests the application's incoming-call HTTP endpoint.

FastAPI returns TwiML instructing Twilio to establish a bidirectional Media Stream. Twilio then opens a WebSocket connection to the application.

The application simultaneously maintains a second WebSocket connection to OpenAI Realtime.

```text
Twilio <-> Python <-> OpenAI
```

Caller audio is streamed to OpenAI and generated audio is streamed back to Twilio in real time.

The OpenAI session and Twilio Media Stream use compatible G.711 μ-law / PCMU telephony audio, allowing audio to be forwarded without an additional transcoding stage.

Python's `asyncio` is used to handle both persistent connections concurrently.

---

## Receptionist Behavior

Business-specific information is separated from the core voice application.

The receptionist can be configured with:

- Business name and description
- Greeting
- Address and phone number
- Business hours
- Specialties
- Services
- Products
- Business practices
- Other static business knowledge

Information that should not be guessed can be explicitly restricted.

For example:

```python
"restricted_information": [
    "Current inventory",
    "Current pricing",
    "Exact product availability",
    "Special-order availability",
]
```

If a caller asks about restricted or unavailable information, the receptionist can offer to take a message or transfer the caller instead of inventing an answer.

---

## Tool Calling

The AI can invoke application-controlled tools during a conversation.

Current tools include:

### Take a Message

Collects structured caller information such as:

- Name
- Phone number
- Reason for calling
- Notes
- Callback request

The message is stored in SQLite and appears in the web dashboard.

### Transfer a Call

The receptionist can transfer an active Twilio call to a configured human destination when the caller needs direct assistance.

The language model determines when a tool is appropriate during the conversation, while the application controls and executes the actual action.

---

## Dashboard

The built-in dashboard provides a simple view of receptionist activity.

Current statistics include:

- Calls
- Call minutes
- Average call duration
- Completed calls
- Messages
- Transfers
- OpenAI cost
- Twilio cost
- Total estimated cost
- Daily cost target
- Recent call history

Caller messages can also be managed through a simple workflow:

```text
New -> Contacted -> Closed
```

The dashboard is intentionally lightweight and requires no frontend framework.

---

## Cost Tracking

One of the primary goals of the project is keeping AI voice practical for small businesses.

The initial design target is:

**≤ $5/day**

OpenAI Realtime usage telemetry is collected for each call, including:

- Input tokens
- Output tokens
- Input audio tokens
- Output audio tokens
- Cached input tokens
- Cached text tokens
- Cached audio tokens

This data is combined with estimated Twilio voice charges to calculate an estimated per-call cost.

Early testing has produced calls costing only a few cents each.

In one test consisting of three calls totaling approximately three minutes, including a normal call, a structured message, and a live transfer, the combined estimated cost was approximately:

**$0.11**

These are development test results, not production cost guarantees. Actual costs depend on call duration, model usage, Twilio pricing, hosting, traffic patterns, and other deployment factors.

---

## Technology

- Python
- FastAPI
- asyncio
- WebSockets
- Twilio Programmable Voice
- Twilio Media Streams
- Twilio REST API
- OpenAI Realtime API
- SQLite
- HTML / CSS / JavaScript
- Cloudflare Tunnel

---

## Setup

### 1. Clone the Repository

```bash
git clone <YOUR-REPOSITORY-URL>
cd AI-SMB-Receptionist
```

### 2. Create a Virtual Environment

Windows:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Business Configuration

The repository contains an example business configuration:

```text
app/business_config.example.py
```

Copy it to:

```text
app/business_config.py
```

Windows:

```powershell
Copy-Item app\business_config.example.py app\business_config.py
```

macOS / Linux:

```bash
cp app/business_config.example.py app/business_config.py
```

Then edit `business_config.py` with information about your business.

The live `business_config.py` file is excluded from Git so each deployment can maintain its own configuration.

---

## Environment Variables

Create a `.env` file in the project root.

The application requires credentials and configuration for OpenAI, Twilio, and the public application URL.

Example:

```env
OPENAI_API_KEY=your_openai_api_key

TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token

PUBLIC_URL=https://your-public-hostname.example
```

Additional environment variables may be required depending on your transfer configuration.

**Never commit `.env`, API keys, Twilio credentials, or other secrets to Git.**

---

## Start the Application

Run FastAPI locally with Uvicorn:

```bash
uvicorn app.main:app --reload
```

The application will run locally at:

```text
http://127.0.0.1:8000
```

Useful local endpoints include:

```text
/          Health check
/inbox     Receptionist dashboard
/messages  Stored caller messages
/calls     Call history
/stats     Usage and cost statistics
/docs      FastAPI API documentation
```

---

## Exposing the Application to Twilio

Twilio must be able to reach the FastAPI application from the public internet.

During development, this project uses **Cloudflare Tunnel** to expose the local Uvicorn server over HTTPS.

For example:

```bash
cloudflared tunnel --url http://localhost:8000
```

Cloudflare will provide a public HTTPS URL.

Set that address as `PUBLIC_URL` in `.env`:

```env
PUBLIC_URL=https://your-tunnel.trycloudflare.com
```

Restart the application after changing `.env`.

Quick tunnels receive a new hostname when restarted. For a permanent deployment, use a named Cloudflare Tunnel with a domain or deploy the application to a publicly reachable host.

---

## Twilio Configuration

Configure the Twilio phone number's incoming voice webhook to send an HTTP `POST` request to:

```text
https://YOUR-PUBLIC-HOSTNAME/incoming-call
```

When a call arrives:

1. Twilio sends the webhook request.
2. FastAPI returns TwiML.
3. Twilio establishes the Media Stream.
4. The application connects to OpenAI Realtime.
5. The receptionist begins the conversation.

---

## Security Notes

This repository is a development project and should be reviewed before production use.

At minimum:

- Keep all credentials in environment variables.
- Never commit `.env`.
- Keep deployment-specific business configuration out of source control.
- Validate Twilio webhook requests.
- Protect administrative/dashboard endpoints.
- Review tool-call authorization and validation.
- Use HTTPS/WSS for all public traffic.
- Review data retention requirements before storing caller information.
- Add production logging, monitoring, and error handling.

---

## Project Status

**Working prototype / active development**

Currently implemented:

- Incoming PSTN calling
- Bidirectional real-time voice
- OpenAI Realtime integration
- Caller interruption handling
- Business-specific knowledge
- Restricted-information guardrails
- Structured message capture
- SQLite persistence
- Message workflow
- Live call transfers
- Call history
- Call outcome tracking
- OpenAI usage telemetry
- Cached-token telemetry
- Twilio/OpenAI cost estimation
- Daily cost dashboard

Potential future work includes:

- Dynamic inventory or business-system integrations
- Smarter after-hours behavior
- Appointment scheduling
- SMS confirmations
- Call summaries
- Additional business configuration
- Production authentication and security
- Deployment automation

---

## License

This project is open source and intended to be used, modified, and improved.

See the repository license for details.

---

## Why This Exists

This project started from a very ordinary small-business problem: sometimes the person who needs to answer the phone is already helping a customer, working with equipment, or simply has both hands occupied.

Modern real-time voice AI has reached a point where handling those calls automatically can be both technically effective and inexpensive.

This repository is available for anyone who wants to experiment with that idea, learn from it, improve it, or adapt it to their own business.