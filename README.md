# Clinic Voice Agent

A production-grade AI voice agent for a healthcare clinic. Patients call a real phone number, speak naturally, and the system books, reschedules, or cancels appointments — with no human operator involved.

Built on a raw voice pipeline (no Vapi/Livekit), a LangGraph multi-agent orchestration layer, ChromaDB RAG, and a live Streamlit ops dashboard.

---

## Architecture

```
Caller (PSTN)
     │
     ▼
Twilio ──WebSocket──▶ FastAPI (voice/server.py)
                           │
                           ▼
                    CallSession (voice/session.py)
                    ┌──────────────────────────────┐
                    │  Deepgram Nova-2  (STT)       │  mulaw → transcript
                    │  LangGraph Graph  (agents)    │  transcript → response text
                    │  ElevenLabs Flash (TTS)       │  response text → mulaw audio
                    └──────────────────────────────┘
                           │
                     per-turn latency logged:
                     [latency] langgraph=0.42s
                     [latency] tts_first_frame=0.38s
                     [latency] turn_total=0.81s

LangGraph Workflow (one turn):

  utterance
     │
     ▼
 sentiment ──▶ intent ──▶ verification ──▶ booking
                  │                    └──▶ reschedule
                  │                    └──▶ cancellation
                  ├──▶ faq
                  └──▶ escalation

SQLite ◀── all agents ──▶ ChromaDB (RAG)
  │
  ▼
Streamlit Dashboard (dashboard/app.py)
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Telephony | Twilio (WebSocket stream, mulaw 8kHz) |
| STT | Deepgram Nova-2, streaming, endpointing 300ms |
| TTS | ElevenLabs `eleven_flash_v2_5`, mulaw output |
| LLM | Groq — LLaMA 3.1 70B (`max_tokens=200` for voice) |
| Agent orchestration | LangGraph `StateGraph` |
| RAG | ChromaDB + `all-MiniLM-L6-v2` embeddings |
| Database | SQLite with optimistic slot locking |
| Server | FastAPI + uvicorn (async WebSocket) |
| Tunnel | ngrok |
| Dashboard | Streamlit (auto-refresh every 2s) |

---

## Agents

| Agent | Role |
|---|---|
| `sentiment_agent` | Keyword-based frustration scoring (0.0–1.0, accumulates across turns). Auto-escalates at 0.75. |
| `intent_agent` | Groq JSON classification: booking / reschedule / cancel / faq / escalate. |
| `verification_agent` | LLM extracts name + DOB → patient DB lookup. Gates all appointment operations. |
| `booking_agent` | Multi-turn state machine: doctor → date → slot → reason → confirm. |
| `reschedule_agent` | Cancels old appointment, pre-fills doctor, delegates to booking flow. |
| `cancellation_agent` | Single-turn: find → cancel → confirm. |
| `faq_agent` | RAG retrieval → Groq grounded answer for clinic policy questions. |
| `escalation_agent` | Graceful handoff. Generates PII-masked call summary. |

---

## Guardrails

- **PII masking** — phone, DOB, email masked in all logs, transcripts, and dashboard.
- **Abuse detection** — personal attacks or profanity → immediate escalation.
- **Scope detection** — out-of-scope questions handled gracefully without crashing the flow.
- **Slot locking** — optimistic lock with 60-second timeout prevents double-booking under concurrent calls.
- **Verification gate** — booking/reschedule/cancel require verified patient identity.

---

## Setup

### 1. Clone and install

```bash
git clone <repo-url>
cd clinic-voice-agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Fill in `.env`:

| Variable | Where to get it |
|---|---|
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) — free tier |
| `DEEPGRAM_API_KEY` | [console.deepgram.com](https://console.deepgram.com) — free tier |
| `ELEVENLABS_API_KEY` | [elevenlabs.io](https://elevenlabs.io) — free tier |
| `ELEVENLABS_VOICE_ID` | Default `ErXwobaYiN019PkySvjV` (Antoni, works on free tier) |
| `TWILIO_ACCOUNT_SID` | [twilio.com/console](https://twilio.com/console) |
| `TWILIO_AUTH_TOKEN` | Twilio console |
| `TWILIO_PHONE_NUMBER` | Your Twilio number |
| `PUBLIC_HOST` | Set after starting ngrok (hostname only, no `https://`) |

### 3. Seed the database

```bash
python seed_database.py
```

Creates `clinic.db` with demo doctors, patients, and appointment slots.

### 4. Ingest the RAG knowledge base

```bash
python -m rag.ingestion
```

Populates `./rag/chroma_db` with clinic knowledge (hours, insurance, services, parking, appointment prep). Re-running is safe (upserts).

### 5. Start the server

```bash
uvicorn voice.server:app --host 0.0.0.0 --port 8000 --reload
```

### 6. Expose with ngrok

```bash
ngrok http 8000
```

Copy the hostname (e.g. `abc123.ngrok-free.app`) and set `PUBLIC_HOST=abc123.ngrok-free.app` in `.env`. Restart the server.

### 7. Configure Twilio webhook

In the Twilio console, set your phone number's "A call comes in" webhook to:

```
https://<your-ngrok-host>/incoming-call
```

### 8. Start the dashboard (optional)

```bash
streamlit run dashboard/app.py
```

Opens at `http://localhost:8501`. Auto-refreshes every 2 seconds.

---

## Demo Scenarios

Call the Twilio number and try these flows:

### Book an appointment
> "I'd like to book an appointment"
> "John Doe, March 5th 1990"
> "Dr. Smith"
> "This Friday"
> "9 AM"
> "Annual checkup"

### Cancel an appointment
> "I need to cancel my appointment"
> "Jane Doe, July 12th 1985"

### Reschedule
> "I need to reschedule"
> "John Doe, March 5th 1990"
> "Next Monday"
> "10 AM"
> "Same reason"

### FAQ
> "What insurance do you accept?"
> "What are your hours?"
> "Where are you located?"

### Trigger escalation
> "This is ridiculous, I want to speak to a manager"

---

## Running Tests

```bash
pytest tests/ -v
```

60 tests across three suites. All Groq/Deepgram/ElevenLabs calls are mocked — no API keys needed.

| Suite | Tests | What it covers |
|---|---|---|
| `test_voice_pipeline.py` | 4 | Session init, state management |
| `test_rag.py` | 6 | Ingestion, retrieval round-trip |
| `test_agents.py` | 50 | All agents, guardrails, booking flow, edge cases |

---

## Project Structure

```
voice/
  server.py          — FastAPI app, /incoming-call + /voice-stream
  twilio_handler.py  — WebSocket loop, per-turn latency logging
  deepgram_stt.py    — Deepgram Nova-2 streaming STT
  elevenlabs_tts.py  — ElevenLabs mulaw frame generator
  session.py         — CallSession: state, LangGraph invoke, TTS speak
  audio_utils.py     — send_mulaw_to_caller helper

agents/
  intent_agent.py        — Groq JSON intent classification
  sentiment_agent.py     — Keyword frustration scoring + abuse check
  verification_agent.py  — LLM name/DOB extraction + patient DB lookup
  booking_agent.py       — Multi-turn slot-filling state machine
  reschedule_agent.py    — Cancel old + delegate to booking
  cancellation_agent.py  — Single-turn cancel
  faq_agent.py           — RAG + Groq grounded answer
  escalation_agent.py    — Handoff + PII-masked call summary

graph/
  state.py     — CallState TypedDict, CallIntent enum
  workflow.py  — LangGraph StateGraph, lazy compilation
  router.py    — route_by_intent(), route_after_verification()
  llm.py       — ChatGroq singleton (max_tokens=200)

db/
  models.py       — SQLite schema + create_tables()
  patients.py     — lookup_patient(), get_patient_by_id()
  doctors.py      — get_all_doctors(), find_doctor_by_name()
  scheduling.py   — lock_slot(), confirm_booking(), cancel_appointment()
  appointments.py — get_patient_appointments()
  call_history.py — start/end call records, dashboard stats

rag/
  ingestion.py          — Chunk + embed clinic markdown files
  vectorstore.py        — ChromaDB query(), format_context()
  clinic_knowledge/     — hours, insurance, services, parking, prep

guardrails/
  pii_masker.py    — mask_pii(), mask_transcript()
  abuse_detector.py — is_abusive()
  scope_detector.py — is_in_scope()

dashboard/
  app.py  — Streamlit ops dashboard (live feed, metrics, escalations)

tests/
  test_voice_pipeline.py
  test_rag.py
  test_agents.py
```

---

## Latency Profile

Per-turn latency is logged to stdout on every call:

```
[latency] langgraph=0.42s        # LangGraph invoke (intent + agent)
[latency] tts_first_frame=0.38s  # ElevenLabs time-to-first-byte
[latency] turn_total=0.81s       # Utterance received → TTS started
```

Typical breakdown:
- Deepgram STT endpointing: ~300ms (configured)
- LangGraph + Groq: 300–600ms
- ElevenLabs first frame: 300–500ms
- **Total perceived latency: ~1.0–1.5s**

---

## Key Design Decisions

**Why raw pipeline instead of Vapi/Livekit?**
Full control over audio encoding, latency, and agent routing. Vapi abstracts these away — useful for production, but you don't learn how voice AI actually works.

**Why LangGraph?**
Stateful multi-agent routing where sentiment can override intent mid-turn. Adding a new agent (e.g. prescription refill) means one new node and one new edge — no rewriting of routing logic.

**Why keyword-based sentiment instead of LLM?**
An LLM call on every turn adds ~300ms latency and token cost. Keyword matching is instant and accurate enough for demo. Score accumulates across turns — a caller who says two frustrated things in a row escalates faster than one who says one.

**How is double-booking prevented?**
Optimistic locking: `lock_slot()` does an `UPDATE ... WHERE locked_until < now()` — atomic at the SQLite level. If it returns 0 rows, the slot was already taken. The taken slot is removed from `available_slots` in state and the caller is presented with remaining options.
