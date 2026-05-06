# Healthcare Clinic Voice Agent
## Complete Project Plan for Implementation

---

## 1. Project Overview

Build a **production-grade voice-based appointment booking agent** for a healthcare clinic.
Patients call a real phone number, speak naturally, and the AI agent handles appointment
booking, rescheduling, cancellations, FAQ answering, and graceful human escalation —
all through a raw voice pipeline you built from scratch.

**Raw Stack:** Twilio → Deepgram → LangGraph → ElevenLabs

No Vapi. No Livekit. You are the orchestrator.

---

## 2. Problem Statement

Healthcare clinics receive hundreds of repetitive phone calls daily:
- "I need to book an appointment with Dr. Smith"
- "Can I reschedule my Tuesday visit?"
- "What are your hours?"
- "Do you accept Blue Cross insurance?"
- "I need to cancel my appointment"

Human receptionists are expensive, unavailable after hours, and overwhelmed.
This voice agent handles 80% of these calls autonomously, escalating only
complex or sensitive cases to a human.

**Input:** Patient phone call (voice)
**Output:** Appointment booked/modified + confirmation + call summary generated

---

## 3. System Architecture

### 3.1 High-Level Voice Pipeline

```
Patient calls Twilio number
        ↓
Twilio streams audio via WebSocket to your FastAPI server
        ↓
Deepgram STT converts audio → text (streaming, real-time)
        ↓
LangGraph multi-agent pipeline processes intent
        ↓
Agent generates response text
        ↓
ElevenLabs TTS converts text → audio (streaming)
        ↓
Audio streamed back to Twilio → patient hears response
        ↓
Loop continues until call ends
        ↓
Call summary generated + dashboard updated
```

### 3.2 LangGraph Agent Flow

```
                    [Incoming utterance]
                           ↓
                    ┌──────────────┐
                    │ Intent Agent │
                    └──────┬───────┘
                           ↓
           ┌───────┬───────┼───────┬──────────┐
           ↓       ↓       ↓       ↓          ↓
      ┌────────┐┌──────┐┌──────┐┌──────┐┌──────────┐
      │Booking ││Resche││Cancel││ FAQ  ││Escalation│
      │ Agent  ││dule  ││Agent ││Agent ││  Agent   │
      └───┬────┘└──┬───┘└──┬───┘└──┬───┘└────┬─────┘
          ↓        ↓       ↓       ↓         ↓
     ┌─────────┐                        ┌─────────┐
     │Verifica-│                        │Human    │
     │tion     │                        │Handoff  │
     │Agent    │                        │+ Summary│
     └────┬────┘                        └─────────┘
          ↓
     ┌─────────┐
     │Slot     │
     │Manager  │
     └────┬────┘
          ↓
     ┌─────────┐
     │Confirma-│
     │tion     │
     └─────────┘
```

### 3.3 Agent Responsibilities

| Agent | Input | Output | Tools |
|---|---|---|---|
| Intent Agent | User utterance + conversation history | Intent label + confidence | None |
| Verification Agent | Patient name/DOB claim | Verified patient ID or failure | Patient DB lookup |
| Booking Agent | Verified patient + preferences | Slot selection conversation | Schedule DB |
| Reschedule Agent | Verified patient + existing booking | Updated appointment | Schedule DB |
| Cancellation Agent | Verified patient + existing booking | Freed slot + confirmation | Schedule DB |
| FAQ Agent | Question text | Grounded answer | RAG retrieval (ChromaDB) |
| Escalation Agent | Conversation so far | Handoff message + summary | Slack webhook |
| Sentiment Agent | Running transcript | Frustration score | Background — always on |

---

## 4. Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Telephony | **Twilio** | Real phone number, WebSocket audio streaming |
| STT | **Deepgram** (Nova-2, streaming) | Low latency, mulaw support, endpointing |
| Agent Orchestration | **LangGraph** (Python) | Multi-agent routing, state management |
| LLM | **Groq** (LLaMA 3.1 70B) | Free tier, fast inference |
| TTS | **ElevenLabs** (Turbo v2, streaming) | Natural voice, streaming chunks |
| RAG / Vector DB | **ChromaDB** | Clinic FAQ knowledge base |
| Scheduling DB | **SQLite** | Doctor availability, appointments |
| Patient DB | **SQLite** | Patient records for verification |
| Audio Conversion | **pydub + ffmpeg** | MP3 → mulaw 8kHz conversion |
| Server | **FastAPI + uvicorn** | Async WebSocket handling |
| Tunnel | **ngrok** | Expose localhost to Twilio |
| Dashboard | **Streamlit** | Ops monitoring, live transcripts |
| Notifications | **Slack webhook** (optional) | Human escalation alerts |
| Environment | Python 3.11+, `.env` | API key management |

---

## 5. Project Structure

```
clinic-voice-agent/
│
├── voice/
│   ├── __init__.py
│   ├── server.py                  # FastAPI app — Twilio webhook + WebSocket
│   ├── twilio_handler.py          # Twilio audio stream handling
│   ├── deepgram_stt.py            # Deepgram streaming transcription
│   ├── elevenlabs_tts.py          # ElevenLabs streaming TTS
│   ├── audio_utils.py             # MP3 → mulaw conversion, audio helpers
│   └── session.py                 # Per-call session state management
│
├── agents/
│   ├── __init__.py
│   ├── intent_agent.py            # Classifies caller intent
│   ├── verification_agent.py      # Verifies patient identity
│   ├── booking_agent.py           # Handles new appointment booking
│   ├── reschedule_agent.py        # Handles appointment rescheduling
│   ├── cancellation_agent.py      # Handles appointment cancellation
│   ├── faq_agent.py               # Answers clinic questions via RAG
│   ├── escalation_agent.py        # Hands off to human receptionist
│   └── sentiment_agent.py         # Background frustration monitoring
│
├── graph/
│   ├── __init__.py
│   ├── workflow.py                # LangGraph state machine definition
│   └── router.py                  # Intent → agent routing logic
│
├── db/
│   ├── __init__.py
│   ├── models.py                  # SQLAlchemy models (doctors, slots, patients)
│   ├── scheduling.py              # Slot management, booking logic, concurrency
│   ├── patients.py                # Patient lookup and verification
│   ├── call_history.py            # Call logs, transcripts, outcomes
│   └── seed_data.py               # Populate DB with demo clinic data
│
├── rag/
│   ├── __init__.py
│   ├── vectorstore.py             # ChromaDB setup and retrieval
│   ├── ingestion.py               # Ingest clinic FAQs and policies
│   └── clinic_knowledge/          # Source markdown files
│       ├── hours_and_location.md
│       ├── insurance_policies.md
│       ├── appointment_prep.md
│       ├── services_offered.md
│       └── parking_and_directions.md
│
├── guardrails/
│   ├── __init__.py
│   ├── pii_masker.py              # Mask names, DOB, phone in logs
│   ├── scope_detector.py          # Detect out-of-scope questions
│   └── abuse_detector.py          # Handle abusive callers
│
├── dashboard/
│   └── app.py                     # Streamlit ops monitoring dashboard
│
├── tests/
│   ├── test_agents.py
│   ├── test_booking.py
│   ├── test_voice_pipeline.py
│   └── test_guardrails.py
│
├── .env.example
├── requirements.txt
├── seed_database.py               # One-time setup script
└── README.md
```

---

## 6. State Schema (LangGraph)

```python
from typing import TypedDict, List, Optional
from enum import Enum

class CallIntent(str, Enum):
    BOOKING = "booking"
    RESCHEDULE = "reschedule"
    CANCEL = "cancel"
    FAQ = "faq"
    ESCALATE = "escalate"
    UNKNOWN = "unknown"

class CallState(TypedDict):
    # Session info
    call_sid: str                          # Twilio call identifier
    stream_sid: str                        # Twilio stream identifier
    caller_phone: str                      # Caller's phone number

    # Conversation
    conversation_history: List[dict]       # [{role: "patient"/"agent", text: "..."}]
    current_utterance: str                 # Latest patient utterance
    agent_response: str                    # Latest agent response text

    # Intent routing
    current_intent: CallIntent             # Classified intent
    intent_confidence: float               # 0.0 to 1.0
    previous_intents: List[CallIntent]     # Track intent changes mid-call

    # Patient verification
    patient_verified: bool                 # Identity confirmed
    patient_id: Optional[int]              # DB patient ID
    patient_name: Optional[str]            # Verified name
    verification_attempts: int             # Max 2 before escalate

    # Booking flow
    requested_doctor: Optional[str]        # Doctor name/preference
    requested_date: Optional[str]          # Preferred date
    requested_time: Optional[str]          # Preferred time
    reason_for_visit: Optional[str]        # Visit reason
    available_slots: List[dict]            # Slots offered to patient
    booked_appointment_id: Optional[int]   # Confirmed booking ID

    # Existing appointment (for reschedule/cancel)
    existing_appointment_id: Optional[int]
    existing_appointment_details: Optional[dict]

    # FAQ
    faq_query: Optional[str]               # Question for RAG
    faq_answer: Optional[str]              # Retrieved answer

    # Sentiment and safety
    frustration_score: float               # 0.0 to 1.0, updated continuously
    guardrail_triggered: Optional[str]     # Which guardrail fired, if any

    # Call metadata
    call_start_time: str                   # ISO timestamp
    turn_count: int                        # Number of conversation turns
    total_latency_ms: float                # Cumulative pipeline latency
    total_tokens_used: int                 # LLM token count
    escalated: bool                        # Whether call was escalated
    call_outcome: Optional[str]            # "booked", "rescheduled", "cancelled",
                                           # "faq_answered", "escalated", "abandoned"
```

---

## 7. Database Schema

### 7.1 Doctors Table

```sql
CREATE TABLE doctors (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,              -- "Dr. Sarah Smith"
    specialty TEXT NOT NULL,         -- "General Practice"
    available_days TEXT NOT NULL,    -- "Mon,Tue,Wed,Thu,Fri"
    slot_duration_minutes INTEGER DEFAULT 30
);
```

### 7.2 Slots Table

```sql
CREATE TABLE slots (
    id INTEGER PRIMARY KEY,
    doctor_id INTEGER REFERENCES doctors(id),
    date TEXT NOT NULL,              -- "2026-05-06"
    start_time TEXT NOT NULL,        -- "10:00"
    end_time TEXT NOT NULL,          -- "10:30"
    is_available BOOLEAN DEFAULT TRUE,
    locked_until TEXT DEFAULT NULL,  -- Temporary lock for concurrency
    locked_by TEXT DEFAULT NULL      -- call_sid that locked it
);
```

### 7.3 Appointments Table

```sql
CREATE TABLE appointments (
    id INTEGER PRIMARY KEY,
    patient_id INTEGER REFERENCES patients(id),
    slot_id INTEGER REFERENCES slots(id),
    doctor_id INTEGER REFERENCES doctors(id),
    date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    reason TEXT,
    status TEXT DEFAULT 'confirmed', -- confirmed, cancelled, rescheduled
    created_at TEXT NOT NULL,
    updated_at TEXT
);
```

### 7.4 Patients Table

```sql
CREATE TABLE patients (
    id INTEGER PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    date_of_birth TEXT NOT NULL,     -- "1990-03-05"
    phone TEXT NOT NULL,
    email TEXT,
    created_at TEXT NOT NULL
);
```

### 7.5 Call History Table

```sql
CREATE TABLE call_history (
    id INTEGER PRIMARY KEY,
    call_sid TEXT NOT NULL,
    caller_phone TEXT NOT NULL,
    patient_id INTEGER REFERENCES patients(id),
    start_time TEXT NOT NULL,
    end_time TEXT,
    duration_seconds INTEGER,
    transcript TEXT,                 -- Full conversation (PII masked)
    intent_sequence TEXT,            -- JSON array of intents
    outcome TEXT,                    -- booked, cancelled, escalated, etc.
    appointment_id INTEGER REFERENCES appointments(id),
    sentiment_avg REAL,
    total_tokens INTEGER,
    total_cost_usd REAL,
    escalated BOOLEAN DEFAULT FALSE,
    call_summary TEXT,               -- Structured summary (auto-generated)
    created_at TEXT NOT NULL
);
```

### 7.6 Concurrency: Slot Locking

The hardest part of scheduling — two calls trying to book the same slot simultaneously.

```python
# db/scheduling.py

import sqlite3
from datetime import datetime, timedelta

LOCK_TIMEOUT_SECONDS = 60  # Lock expires after 60 seconds

def lock_slot(slot_id: int, call_sid: str, db_path: str) -> bool:
    """
    Attempt to temporarily lock a slot for this call.
    Returns True if lock acquired, False if slot already locked/taken.
    """
    conn = sqlite3.connect(db_path)
    now = datetime.utcnow().isoformat()
    expiry = (datetime.utcnow() + timedelta(seconds=LOCK_TIMEOUT_SECONDS)).isoformat()

    # Clear expired locks first
    conn.execute(
        "UPDATE slots SET locked_until = NULL, locked_by = NULL "
        "WHERE locked_until IS NOT NULL AND locked_until < ?",
        (now,)
    )

    # Try to lock
    cursor = conn.execute(
        "UPDATE slots SET locked_until = ?, locked_by = ? "
        "WHERE id = ? AND is_available = 1 "
        "AND (locked_until IS NULL OR locked_until < ? OR locked_by = ?)",
        (expiry, call_sid, slot_id, now, call_sid)
    )
    conn.commit()

    success = cursor.rowcount > 0
    conn.close()
    return success

def confirm_booking(slot_id: int, call_sid: str, patient_id: int, reason: str, db_path: str) -> int:
    """
    Convert a locked slot into a confirmed appointment.
    Returns appointment_id.
    """
    conn = sqlite3.connect(db_path)

    # Verify this call holds the lock
    row = conn.execute(
        "SELECT doctor_id, date, start_time FROM slots "
        "WHERE id = ? AND locked_by = ?",
        (slot_id, call_sid)
    ).fetchone()

    if not row:
        conn.close()
        raise Exception("Slot not locked by this call")

    doctor_id, date, start_time = row

    # Mark slot as taken
    conn.execute(
        "UPDATE slots SET is_available = 0, locked_until = NULL, locked_by = NULL "
        "WHERE id = ?",
        (slot_id,)
    )

    # Create appointment
    now = datetime.utcnow().isoformat()
    cursor = conn.execute(
        "INSERT INTO appointments (patient_id, slot_id, doctor_id, date, start_time, reason, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'confirmed', ?)",
        (patient_id, slot_id, doctor_id, date, start_time, reason, now)
    )
    conn.commit()

    appointment_id = cursor.lastrowid
    conn.close()
    return appointment_id

def get_available_slots(doctor_id: int, date: str, db_path: str) -> list:
    """Get available slots for a doctor on a given date."""
    conn = sqlite3.connect(db_path)
    now = datetime.utcnow().isoformat()

    rows = conn.execute(
        "SELECT id, start_time, end_time FROM slots "
        "WHERE doctor_id = ? AND date = ? AND is_available = 1 "
        "AND (locked_until IS NULL OR locked_until < ?)"
        "ORDER BY start_time",
        (doctor_id, date, now)
    ).fetchall()
    conn.close()

    return [{"slot_id": r[0], "start_time": r[1], "end_time": r[2]} for r in rows]
```

---

## 8. Agent Implementation Details

### 8.1 Intent Agent

**Purpose:** Classify every patient utterance into one of the known intents.

**Prompt:**
```
You are an intent classifier for a healthcare clinic phone system.
Given the patient's utterance and conversation history, classify the intent.

Possible intents:
- booking: Patient wants to schedule a new appointment
- reschedule: Patient wants to change an existing appointment
- cancel: Patient wants to cancel an existing appointment
- faq: Patient is asking a general question about the clinic
- escalate: Patient explicitly asks for a human or is too frustrated
- unknown: Cannot determine intent

Respond with JSON only:
{"intent": "booking", "confidence": 0.95}
```

**Key logic:**
```python
def intent_agent(state: CallState) -> CallState:
    # Include last 3 turns of conversation for context
    history = state["conversation_history"][-6:]  # 3 turns = 6 messages
    utterance = state["current_utterance"]

    result = call_llm(intent_prompt, history, utterance)

    state["current_intent"] = result["intent"]
    state["intent_confidence"] = result["confidence"]
    state["previous_intents"].append(result["intent"])

    # Auto-escalate if confidence is too low
    if result["confidence"] < 0.5:
        state["current_intent"] = CallIntent.ESCALATE

    return state
```

---

### 8.2 Verification Agent

**Purpose:** Confirm patient identity before allowing booking/reschedule/cancel.

**Flow:**
```
Agent: "Can I have your full name, please?"
Patient: "John Doe"
Agent: "And your date of birth for verification?"
Patient: "March 5th, 1990"
→ Look up in patients DB
→ If match found: patient_verified = True
→ If no match after 2 attempts: escalate
```

**Key logic:**
```python
def verification_agent(state: CallState) -> CallState:
    # Skip if already verified
    if state["patient_verified"]:
        return state

    utterance = state["current_utterance"]

    # Use LLM to extract name and DOB from natural speech
    extracted = call_llm(extraction_prompt, utterance)
    # Returns: {"name": "John Doe", "dob": "1990-03-05"}

    # Look up patient in DB
    patient = lookup_patient(extracted["name"], extracted["dob"])

    if patient:
        state["patient_verified"] = True
        state["patient_id"] = patient["id"]
        state["patient_name"] = patient["first_name"]
        state["agent_response"] = f"Thank you, {patient['first_name']}. I've verified your identity. How can I help you today?"
    else:
        state["verification_attempts"] += 1
        if state["verification_attempts"] >= 2:
            state["current_intent"] = CallIntent.ESCALATE
            state["agent_response"] = "I'm having trouble verifying your identity. Let me connect you with our front desk."
        else:
            state["agent_response"] = "I couldn't find that in our records. Could you please repeat your full name and date of birth?"

    return state
```

---

### 8.3 Booking Agent

**Purpose:** Multi-turn slot-filling conversation to book an appointment.

**Slots to fill:**
1. Doctor preference (or "any available")
2. Preferred date
3. Preferred time
4. Reason for visit

**Flow:**
```
Agent: "Which doctor would you like to see?"
Patient: "Dr. Smith"
Agent: "What date works for you?"
Patient: "Next Tuesday"
Agent: "Dr. Smith has 10:00 AM and 2:00 PM available on Tuesday. Which do you prefer?"
Patient: "10 AM"
Agent: "And what's the reason for your visit?"
Patient: "Annual checkup"
Agent: "I've booked you with Dr. Smith on Tuesday May 6th at 10:00 AM
        for an annual checkup. Is there anything else I can help with?"
```

**Key logic:**
```python
def booking_agent(state: CallState) -> CallState:
    utterance = state["current_utterance"]

    # Use LLM to extract any new slot values from utterance
    extracted = call_llm(slot_extraction_prompt, utterance, state)

    # Update state with extracted values
    if extracted.get("doctor"):
        state["requested_doctor"] = extracted["doctor"]
    if extracted.get("date"):
        state["requested_date"] = extracted["date"]
    if extracted.get("time"):
        state["requested_time"] = extracted["time"]
    if extracted.get("reason"):
        state["reason_for_visit"] = extracted["reason"]

    # Determine what's still missing
    missing = get_missing_slots(state)

    if not missing:
        # All slots filled — attempt to book
        doctor_id = get_doctor_id(state["requested_doctor"])
        slot = find_matching_slot(doctor_id, state["requested_date"], state["requested_time"])

        if slot and lock_slot(slot["slot_id"], state["call_sid"]):
            appointment_id = confirm_booking(
                slot["slot_id"], state["call_sid"],
                state["patient_id"], state["reason_for_visit"]
            )
            state["booked_appointment_id"] = appointment_id
            state["call_outcome"] = "booked"
            state["agent_response"] = generate_confirmation_message(state)
        else:
            # Slot taken between offer and confirmation
            state["agent_response"] = "I'm sorry, that slot was just taken. Let me check other available times."
            state["requested_time"] = None  # Reset time to re-offer

    elif "doctor" in missing:
        state["agent_response"] = "Which doctor would you like to see? We have Dr. Smith, Dr. Patel, and Dr. Johnson available."

    elif "date" in missing:
        state["agent_response"] = f"What date would you like to see {state['requested_doctor']}?"

    elif "time" in missing:
        # Fetch and present available slots
        slots = get_available_slots(doctor_id, state["requested_date"])
        state["available_slots"] = slots
        times = ", ".join([s["start_time"] for s in slots[:4]])
        state["agent_response"] = f"{state['requested_doctor']} has these times available: {times}. Which works best?"

    elif "reason" in missing:
        state["agent_response"] = "And what's the reason for your visit?"

    return state
```

---

### 8.4 Reschedule Agent

**Purpose:** Find existing appointment, free old slot, book new slot.

```python
def reschedule_agent(state: CallState) -> CallState:
    # Find existing appointment
    if not state["existing_appointment_id"]:
        appointment = find_appointment_by_patient(state["patient_id"])
        if appointment:
            state["existing_appointment_id"] = appointment["id"]
            state["existing_appointment_details"] = appointment
            state["agent_response"] = (
                f"I found your appointment with {appointment['doctor_name']} "
                f"on {appointment['date']} at {appointment['start_time']}. "
                f"What date and time would you like to change it to?"
            )
        else:
            state["agent_response"] = "I don't see any upcoming appointments in your name. Would you like to book a new one?"
            state["current_intent"] = CallIntent.BOOKING
        return state

    # Collect new date/time same as booking agent
    # Then: free old slot, book new slot
    # ...
```

---

### 8.5 Cancellation Agent

```python
def cancellation_agent(state: CallState) -> CallState:
    if not state["existing_appointment_id"]:
        appointment = find_appointment_by_patient(state["patient_id"])
        if appointment:
            state["existing_appointment_details"] = appointment
            state["agent_response"] = (
                f"I found your appointment with {appointment['doctor_name']} "
                f"on {appointment['date']} at {appointment['start_time']}. "
                f"Are you sure you'd like to cancel?"
            )
        else:
            state["agent_response"] = "I don't see any upcoming appointments to cancel."
        return state

    # Patient confirmed cancellation
    if is_confirmation(state["current_utterance"]):
        cancel_appointment(state["existing_appointment_id"])
        free_slot(state["existing_appointment_details"]["slot_id"])
        state["call_outcome"] = "cancelled"
        state["agent_response"] = "Your appointment has been cancelled. Is there anything else I can help with?"
    else:
        state["agent_response"] = "No problem, your appointment is still confirmed. Anything else?"

    return state
```

---

### 8.6 FAQ Agent (RAG-enabled)

**Purpose:** Answer clinic questions using knowledge base.

```python
def faq_agent(state: CallState) -> CallState:
    query = state["current_utterance"]

    # Retrieve relevant context from ChromaDB
    context = vectorstore.query(query, top_k=3)

    # Generate grounded answer
    answer = call_llm(
        faq_prompt,
        query=query,
        context=context,
        instruction="Answer the patient's question using ONLY the provided context. "
                    "If the answer is not in the context, say you'll connect them "
                    "with the front desk for more details."
    )

    state["faq_query"] = query
    state["faq_answer"] = answer
    state["agent_response"] = answer
    return state
```

---

### 8.7 Escalation Agent

**Purpose:** Hand off to human receptionist gracefully.

```python
def escalation_agent(state: CallState) -> CallState:
    # Generate call summary for human
    summary = call_llm(
        summary_prompt,
        conversation=state["conversation_history"],
        patient_name=state.get("patient_name", "Unknown"),
        intent=state["current_intent"],
        reason="Low confidence" if state["intent_confidence"] < 0.5
               else "Patient requested" if "human" in state["current_utterance"].lower()
               else f"Frustration detected (score: {state['frustration_score']:.2f})"
    )

    # Send to Slack (optional)
    send_slack_notification(
        channel="#clinic-escalations",
        text=f"🚨 Call escalation\n"
             f"Patient: {state.get('patient_name', 'Unverified')}\n"
             f"Phone: {mask_pii(state['caller_phone'])}\n"
             f"Reason: {summary}\n"
             f"Transcript: {mask_pii(format_transcript(state['conversation_history']))}"
    )

    state["escalated"] = True
    state["call_outcome"] = "escalated"
    state["agent_response"] = (
        "I understand. Let me connect you with our front desk team. "
        "They'll have a summary of our conversation so you won't need to repeat yourself. "
        "Please hold for a moment."
    )

    # Store call summary
    store_call_summary(state["call_sid"], summary)

    return state
```

---

### 8.8 Sentiment Agent (Background)

**Purpose:** Runs after every utterance to detect frustration.

```python
def sentiment_agent(state: CallState) -> CallState:
    # Analyze last 3 patient utterances for frustration signals
    recent = [m["text"] for m in state["conversation_history"][-6:] if m["role"] == "patient"]

    score = call_llm(
        sentiment_prompt,
        utterances=recent,
        instruction="Rate the caller's frustration from 0.0 (calm) to 1.0 (very frustrated). "
                    "Consider: repeated questions, raised voice indicators (ALL CAPS, exclamation marks), "
                    "phrases like 'this is ridiculous', 'let me speak to someone'. "
                    "Respond with JSON: {\"score\": 0.7, \"reason\": \"repeated same question 3 times\"}"
    )

    state["frustration_score"] = score["score"]

    # Auto-escalate if frustration is high
    if score["score"] > 0.8:
        state["current_intent"] = CallIntent.ESCALATE

    return state
```

---

## 9. LangGraph Workflow Definition

```python
from langgraph.graph import StateGraph, END

def build_workflow():
    workflow = StateGraph(CallState)

    # Add nodes
    workflow.add_node("sentiment", sentiment_agent)
    workflow.add_node("intent", intent_agent)
    workflow.add_node("verification", verification_agent)
    workflow.add_node("booking", booking_agent)
    workflow.add_node("reschedule", reschedule_agent)
    workflow.add_node("cancellation", cancellation_agent)
    workflow.add_node("faq", faq_agent)
    workflow.add_node("escalation", escalation_agent)

    # Entry: always run sentiment first, then intent
    workflow.set_entry_point("sentiment")
    workflow.add_edge("sentiment", "intent")

    # Intent routes to specialist agent
    workflow.add_conditional_edges(
        "intent",
        route_by_intent,
        {
            "booking": "verification",
            "reschedule": "verification",
            "cancel": "verification",
            "faq": "faq",
            "escalate": "escalation",
            "unknown": "escalation",
        }
    )

    # Verification routes to the actual specialist
    workflow.add_conditional_edges(
        "verification",
        route_after_verification,
        {
            "booking": "booking",
            "reschedule": "reschedule",
            "cancel": "cancellation",
            "escalate": "escalation",      # Verification failed
            "need_more_info": END,          # Ask patient again
        }
    )

    # Terminal nodes
    workflow.add_edge("booking", END)
    workflow.add_edge("reschedule", END)
    workflow.add_edge("cancellation", END)
    workflow.add_edge("faq", END)
    workflow.add_edge("escalation", END)

    return workflow.compile()


def route_by_intent(state: CallState) -> str:
    intent = state["current_intent"]
    if intent == CallIntent.BOOKING:
        return "booking"
    elif intent == CallIntent.RESCHEDULE:
        return "reschedule"
    elif intent == CallIntent.CANCEL:
        return "cancel"
    elif intent == CallIntent.FAQ:
        return "faq"
    else:
        return "escalate"


def route_after_verification(state: CallState) -> str:
    if not state["patient_verified"]:
        if state["verification_attempts"] >= 2:
            return "escalate"
        return "need_more_info"

    # Route to original intent
    return state["current_intent"].value
```

---

## 10. Voice Pipeline Integration

### 10.1 Main Server

```python
# voice/server.py
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response
import asyncio
import json

app = FastAPI()
compiled_graph = build_workflow()

@app.post("/incoming-call")
async def incoming_call(request: Request):
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Say>Welcome to Sunrise Health Clinic. How can I help you today?</Say>
        <Connect>
            <Stream url="wss://{NGROK_URL}/voice-stream"/>
        </Connect>
    </Response>"""
    return Response(content=twiml, media_type="application/xml")

@app.websocket("/voice-stream")
async def voice_stream(websocket: WebSocket):
    await websocket.accept()
    session = CallSession()

    async for message in websocket.iter_text():
        data = json.loads(message)

        if data["event"] == "start":
            session.stream_sid = data["start"]["streamSid"]
            session.call_sid = data["start"]["callSid"]

        elif data["event"] == "media":
            audio_bytes = base64.b64decode(data["media"]["payload"])
            await session.audio_queue.put(audio_bytes)

        elif data["event"] == "stop":
            await session.audio_queue.put(None)
            await session.end_call()
            break

    # Generate call summary
    await generate_and_store_call_summary(session)
```

### 10.2 Session Manager

```python
# voice/session.py
class CallSession:
    def __init__(self):
        self.call_sid = None
        self.stream_sid = None
        self.audio_queue = asyncio.Queue()
        self.state = initial_call_state()
        self.speaking = False
        self.speak_task = None

    async def process_turn(self, transcript: str, websocket):
        """Full turn: transcript → LangGraph → TTS → send audio"""
        # Update state
        self.state["current_utterance"] = transcript
        self.state["conversation_history"].append(
            {"role": "patient", "text": transcript}
        )
        self.state["turn_count"] += 1

        # Run LangGraph
        start = time.time()
        result = await asyncio.to_thread(
            compiled_graph.invoke, self.state
        )
        self.state = result
        latency = (time.time() - start) * 1000
        self.state["total_latency_ms"] += latency

        response_text = self.state["agent_response"]
        self.state["conversation_history"].append(
            {"role": "agent", "text": response_text}
        )

        # Stream TTS back to caller
        self.speaking = True
        self.speak_task = asyncio.create_task(
            stream_tts_to_twilio(response_text, websocket, self.stream_sid)
        )
        await self.speak_task
        self.speaking = False

    async def handle_interruption(self):
        """Cancel TTS if patient starts speaking"""
        if self.speaking and self.speak_task:
            self.speak_task.cancel()
            self.speaking = False
```

---

## 11. PII Masking

```python
# guardrails/pii_masker.py
import re

def mask_pii(text: str) -> str:
    """Mask sensitive information in text for logging and dashboard."""

    # Phone numbers
    text = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '***-***-****', text)

    # SSN pattern
    text = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '***-**-****', text)

    # Date of birth patterns
    text = re.sub(
        r'\b(January|February|March|April|May|June|July|August|September|'
        r'October|November|December)\s+\d{1,2}(st|nd|rd|th)?,?\s*\d{4}\b',
        '[DOB REDACTED]', text, flags=re.IGNORECASE
    )
    text = re.sub(r'\b\d{1,2}/\d{1,2}/\d{2,4}\b', '[DOB REDACTED]', text)

    # Email
    text = re.sub(r'\b[\w.+-]+@[\w-]+\.[\w.]+\b', '[EMAIL REDACTED]', text)

    return text
```

---

## 12. Structured Call Summary

Auto-generated after every call ends:

```python
# Called at end of each call
def generate_call_summary(state: CallState) -> str:
    summary = call_llm(
        summary_prompt,
        conversation=state["conversation_history"],
        instruction="""
        Generate a structured call summary in this exact format:

        Patient: [name or 'Unverified']
        Call Duration: [duration]
        Primary Intent: [booking/reschedule/cancel/faq/escalation]
        Outcome: [what happened]
        Appointment Details: [if applicable — doctor, date, time, reason]
        Notes: [any relevant context for follow-up]
        Escalated: [Yes/No — if yes, reason]
        """
    )
    return summary
```

**Example output:**
```
Patient: John Doe
Call Duration: 2m 14s
Primary Intent: New appointment booking
Outcome: Successfully booked
Appointment Details: Dr. Smith, Tuesday May 6, 10:00 AM, Annual checkup
Notes: Patient requested morning slots only
Escalated: No
```

---

## 13. Streamlit Ops Dashboard (dashboard/app.py)

### Layout

```
┌─────────────────────────────────────────────────────────────┐
│  🏥 Sunrise Health Clinic — Voice Agent Dashboard            │
├──────────┬──────────┬──────────┬──────────┬─────────────────┤
│ Active   │ Today's  │ Success  │ Avg      │ Total Cost      │
│ Calls: 1 │ Calls: 23│ Rate: 87%│ Time: 95s│ Today: $0.42    │
├──────────┴──────────┴──────────┴──────────┴─────────────────┤
│                                                              │
│  📞 LIVE CALL FEED                                           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 2:34 PM | John Doe | Booking | Dr. Smith, Tue 10AM  │   │
│  │ Status: ✅ Confirmed                                 │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │ 2:31 PM | Jane Roe | FAQ | Insurance question       │   │
│  │ Status: ✅ Answered                                   │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │ 2:28 PM | Unknown  | Booking | Verification failed  │   │
│  │ Status: 🔴 Escalated                                 │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  TABS: [Transcript] [Agent Path] [Metrics] [Escalations]    │
│                                                              │
│  Transcript Tab:                                             │
│  Patient: "I need to see Dr. Smith next Tuesday"             │
│  → Intent Agent: booking (0.97)                              │
│  → Verification Agent: verified (John Doe)                   │
│  → Booking Agent: checking slots...                          │
│  Agent: "Dr. Smith has 10 AM and 2 PM. Which works?"         │
│  Patient: "10 AM please"                                     │
│  → Booking Agent: slot locked → confirmed                    │
│  Agent: "You're confirmed for Tuesday at 10 AM."             │
│                                                              │
│  Metrics Tab:                                                │
│  [Bar chart: calls by intent]                                │
│  [Line chart: latency per stage over time]                   │
│  [Pie chart: outcomes — booked/cancelled/escalated]          │
│                                                              │
│  Escalation Queue Tab:                                       │
│  🔴 2:28 PM | Unknown caller | Verification failed x2       │
│     Summary: Caller could not verify identity...             │
│     [Call Back] [Mark Resolved]                               │
└─────────────────────────────────────────────────────────────┘
```

### Key Streamlit components:
- `st.metric()` — top row KPIs
- `st.status()` — live agent activity
- `st.tabs()` — Transcript, Agent Path, Metrics, Escalations
- `st.dataframe()` — call history table
- `st.bar_chart()` / `st.line_chart()` — analytics
- Auto-refresh using `st.rerun()` with `time.sleep(2)` polling
- Read from call_history SQLite table

---

## 14. RAG Knowledge Base Setup

### 14.1 Sample Clinic Knowledge Files

**rag/clinic_knowledge/hours_and_location.md**
```markdown
# Sunrise Health Clinic — Hours & Location

Address: 4521 W Main Street, Suite 200, Tempe, AZ 85281
Phone: (480) 555-0100

Hours of Operation:
- Monday to Friday: 8:00 AM – 6:00 PM
- Saturday: 9:00 AM – 1:00 PM
- Sunday: Closed

Holiday closures: The clinic is closed on all major federal holidays.
After-hours urgent care: Call (480) 555-0199 for the on-call nurse line.
```

**rag/clinic_knowledge/insurance_policies.md**
```markdown
# Insurance Policies

Accepted insurance providers:
- Blue Cross Blue Shield
- Aetna
- UnitedHealthcare
- Cigna
- Medicare
- Medicaid (AHCCCS in Arizona)

Co-pay is due at the time of visit.
We do not accept out-of-network claims.
For insurance verification, please bring your insurance card to your appointment.
Questions about coverage should be directed to your insurance provider.
```

**rag/clinic_knowledge/appointment_prep.md**
```markdown
# Appointment Preparation

For a general checkup:
- No special preparation needed
- Bring a list of current medications
- Arrive 15 minutes early for paperwork

For lab work / blood tests:
- Fast for 8-12 hours before your appointment
- Drink water as normal
- Bring your insurance card and photo ID

For new patients:
- Complete the new patient form (available on our website or at the front desk)
- Bring photo ID and insurance card
- Arrive 30 minutes early
```

### 14.2 Ingestion

```python
# rag/ingestion.py
import chromadb
from sentence_transformers import SentenceTransformer
import os

def ingest_clinic_knowledge(knowledge_dir: str, collection_name: str = "clinic_faq"):
    model = SentenceTransformer("all-MiniLM-L6-v2")
    client = chromadb.PersistentClient(path="./rag/chroma_db")
    collection = client.get_or_create_collection(collection_name)

    for filename in os.listdir(knowledge_dir):
        if filename.endswith(".md"):
            filepath = os.path.join(knowledge_dir, filename)
            with open(filepath, "r") as f:
                content = f.read()

            # Chunk by sections
            chunks = content.split("\n\n")
            for i, chunk in enumerate(chunks):
                chunk = chunk.strip()
                if len(chunk) < 20:
                    continue
                doc_id = f"{filename}_{i}"
                embedding = model.encode(chunk).tolist()
                collection.upsert(
                    documents=[chunk],
                    embeddings=[embedding],
                    ids=[doc_id],
                    metadatas=[{"source": filename}]
                )

    print(f"Ingested {collection.count()} chunks into ChromaDB")
```

---

## 15. Seed Data

```python
# seed_database.py
import sqlite3
from datetime import datetime, timedelta

def seed():
    conn = sqlite3.connect("clinic.db")

    # Create tables (run schema from section 7)
    conn.executescript(SCHEMA_SQL)

    # Doctors
    doctors = [
        (1, "Dr. Sarah Smith", "General Practice", "Mon,Tue,Wed,Thu,Fri", 30),
        (2, "Dr. Raj Patel", "Internal Medicine", "Mon,Tue,Wed,Thu", 30),
        (3, "Dr. Emily Johnson", "Pediatrics", "Mon,Wed,Fri", 30),
        (4, "Dr. Michael Chen", "Dermatology", "Tue,Thu", 45),
    ]
    conn.executemany("INSERT INTO doctors VALUES (?,?,?,?,?)", doctors)

    # Generate slots for next 14 days
    for doctor in doctors:
        doctor_id, _, _, available_days, duration = doctor
        day_map = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5}

        for day_offset in range(14):
            date = datetime.now().date() + timedelta(days=day_offset)
            day_name = date.strftime("%a")

            if day_name not in available_days:
                continue

            # Generate slots from 8 AM to 5 PM
            hour = 8
            while hour < 17:
                start = f"{hour:02d}:00"
                end_hour = hour + (duration // 60)
                end_min = duration % 60
                end = f"{end_hour:02d}:{end_min:02d}"

                conn.execute(
                    "INSERT INTO slots (doctor_id, date, start_time, end_time, is_available) "
                    "VALUES (?, ?, ?, ?, 1)",
                    (doctor_id, date.isoformat(), start, end)
                )
                hour += 1 if duration == 30 else 1

    # Sample patients
    patients = [
        (1, "John", "Doe", "1990-03-05", "4805551234", "john@email.com"),
        (2, "Jane", "Roe", "1985-07-22", "4805555678", "jane@email.com"),
        (3, "Aditya", "Rallapalli", "1998-01-15", "4805559012", "aditya@email.com"),
        (4, "Maria", "Garcia", "1975-11-30", "4805553456", "maria@email.com"),
    ]
    conn.executemany(
        "INSERT INTO patients VALUES (?,?,?,?,?,?, datetime('now'))",
        patients
    )

    conn.commit()
    conn.close()
    print("Database seeded successfully")

if __name__ == "__main__":
    seed()
```

---

## 16. Fallback Policies

```python
# Fallback rules applied throughout the pipeline

FALLBACK_RULES = {
    # Verification
    "max_verification_attempts": 2,
    "on_verification_fail": "escalate",

    # Intent
    "min_intent_confidence": 0.5,
    "on_low_confidence": "escalate",

    # Sentiment
    "frustration_escalation_threshold": 0.8,

    # Audio quality
    "max_empty_transcripts": 3,  # 3 empty transcripts in a row
    "on_poor_audio": "ask_to_repeat_then_escalate",

    # Booking
    "slot_lock_timeout_seconds": 60,
    "max_booking_turns": 10,  # Prevent infinite loops
    "on_max_turns": "escalate",

    # General
    "max_call_duration_seconds": 300,  # 5 minutes
    "on_timeout": "warn_then_end",
}
```

---

## 17. Requirements

```
# requirements.txt
# Voice pipeline
fastapi>=0.115.0
uvicorn>=0.30.0
websockets>=12.0

# Twilio
twilio>=9.0.0

# STT
deepgram-sdk>=3.5.0

# TTS
elevenlabs>=1.5.0

# Audio
pydub>=0.25.1

# Agent orchestration
langgraph>=0.2.0
langchain>=0.3.0
langchain-groq>=0.2.0

# RAG
chromadb>=0.5.0
sentence-transformers>=3.0.0

# Database
sqlalchemy>=2.0.0

# Dashboard
streamlit>=1.38.0

# Utilities
python-dotenv>=1.0.0
httpx>=0.27.0
```

---

## 18. Environment Variables

```
# .env.example
GROQ_API_KEY=your_groq_api_key
DEEPGRAM_API_KEY=your_deepgram_api_key
ELEVENLABS_API_KEY=your_elevenlabs_api_key
ELEVENLABS_VOICE_ID=ErXwobaYiN019PkySvjV

TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_PHONE_NUMBER=your_twilio_phone_number

NGROK_URL=your_ngrok_url

SLACK_WEBHOOK_URL=your_slack_webhook  # Optional

DB_PATH=./clinic.db
CHROMA_PERSIST_DIR=./rag/chroma_db

LLM_MODEL=llama-3.1-70b-versatile
MAX_RETRIES=3
SLOT_LOCK_TIMEOUT=60
```

---

## 19. Implementation Order (Recommended)

Build in this sequence. Each phase produces a working, testable system.

### Phase 1: Foundation (Day 1)
1. Set up project structure and install dependencies
2. Copy your working Day 4 voice pipeline code as starting point
3. Set up SQLite database with schema from Section 7
4. Run seed_database.py to populate demo data
5. **Test:** Verify DB has doctors, slots, and patients

### Phase 2: RAG Setup (Day 2)
6. Write clinic knowledge markdown files
7. Implement ChromaDB ingestion
8. Build FAQ retrieval function
9. **Test:** Query "what are your hours?" returns correct answer

### Phase 3: LangGraph Skeleton (Day 2-3)
10. Define CallState schema
11. Build LangGraph workflow with placeholder agents
12. Implement Intent Agent (first real agent)
13. Implement FAQ Agent connected to RAG
14. **Test:** Call → say "what are your hours?" → hear correct answer via TTS

### Phase 4: Verification + Booking (Day 3-4)
15. Implement Verification Agent
16. Implement Booking Agent with slot filling
17. Implement slot locking and confirm_booking
18. **Test:** Full booking flow — verify identity → pick doctor → pick slot → confirm

### Phase 5: Reschedule + Cancel (Day 4-5)
19. Implement Reschedule Agent
20. Implement Cancellation Agent
21. **Test:** Book, then reschedule, then cancel in separate calls

### Phase 6: Safety Layer (Day 5-6)
22. Implement Sentiment Agent
23. Implement Escalation Agent with call summary
24. Implement PII masking
25. Implement guardrails (out-of-scope, abuse detection)
26. Implement fallback policies
27. **Test:** Say aggressive things → agent escalates gracefully

### Phase 7: Dashboard (Day 6-7)
28. Build Streamlit app reading from call_history DB
29. Add live call feed with auto-refresh
30. Add transcript viewer with agent path highlighting
31. Add metrics charts
32. Add escalation queue
33. **Test:** Make 5 calls, verify dashboard shows all data correctly

### Phase 8: Polish (Day 7-8)
34. End-to-end test with 5 different call scenarios
35. Optimize latency (measure each stage)
36. Write README with architecture diagram and demo instructions
37. Record demo video (split screen: phone + dashboard)

---

## 20. Demo Script (for Interviews / README)

**Scenario 1: New Appointment Booking**
```
Call your Twilio number
Agent: "Welcome to Sunrise Health Clinic. How can I help you today?"
You: "I need to book an appointment with Dr. Smith"
Agent: "Can I have your full name please?"
You: "John Doe"
Agent: "And your date of birth for verification?"
You: "March 5th, 1990"
Agent: "Thank you, John. What date would you like to see Dr. Smith?"
You: "Next Tuesday"
Agent: "Dr. Smith has 10:00 AM and 2:00 PM available. Which works best?"
You: "10 AM"
Agent: "And what's the reason for your visit?"
You: "Annual checkup"
Agent: "You're confirmed with Dr. Smith on Tuesday May 6th at 10 AM
        for an annual checkup. Is there anything else?"
You: "No, thank you"
Agent: "Have a great day, John. Goodbye!"
```

**Scenario 2: FAQ Question**
```
You: "What insurance do you accept?"
Agent: "We accept Blue Cross Blue Shield, Aetna, UnitedHealthcare,
        Cigna, Medicare, and Medicaid. Co-pay is due at the time of visit.
        Would you like to schedule an appointment?"
```

**Scenario 3: Escalation**
```
You: "I want to talk to a real person"
Agent: "I understand. Let me connect you with our front desk team.
        They'll have a summary of our conversation. Please hold."
→ Slack notification fires with call summary
→ Dashboard shows escalation in real time
```

**Dashboard during demo:**
Open Streamlit on a second screen. As each call happens, the dashboard
updates in real time showing the transcript, agent decisions, and metrics.

---

## 21. Key Interview Talking Points

**Q: Why raw stack instead of Vapi or Livekit?**
"I wanted full control over every layer — audio encoding, latency optimization,
interruption handling, and agent routing. Vapi abstracts these away, which is
great for production but doesn't teach you how voice AI actually works."

**Q: How do you handle two callers booking the same slot?**
"I implemented optimistic locking. When a caller selects a slot, I temporarily
lock it for 60 seconds using a lock timestamp in the database. If the lock
expires without confirmation, the slot becomes available again. This prevents
double-booking without requiring a full transaction queue."

**Q: Why LangGraph instead of a simple if/else router?**
"Three reasons. First, the conversation is stateful — each agent reads from
and writes to shared state, and LangGraph manages that cleanly. Second, the
routing isn't simple — sentiment can override intent at any point and redirect
to escalation. Third, adding new agents (like a prescription refill agent)
means adding one node and one edge, not rewriting routing logic."

**Q: How do you handle poor audio quality?**
"Deepgram sometimes returns empty transcripts when audio quality is low.
I track consecutive empty transcripts — after 3, the agent says 'I'm having
trouble hearing you, could you speak a bit louder?' After 5, it offers to
call back or escalate."

**Q: What's the average latency per turn?**
"About 1.5-2.5 seconds end to end. The breakdown is roughly: Deepgram STT
200-400ms, LangGraph agent 300-600ms (Groq is fast), ElevenLabs TTS
400-800ms, audio conversion and streaming 100-200ms. The bottleneck is
usually TTS, which is why I stream chunks rather than waiting for full audio."

**Q: How does interruption handling work?**
"I use asyncio task cancellation. The TTS playback runs as an async task.
If new audio arrives from Deepgram while TTS is playing, I cancel the TTS
task immediately and process the new utterance. The patient experiences
this as: they start speaking, the agent stops and listens."

**Q: What would you add in production?**
"Real Google Calendar integration instead of SQLite, HIPAA-compliant logging
with encrypted storage, load testing for concurrent calls, a proper
queuing system for escalated calls, and automated integration tests that
simulate full phone conversations."

---

## 22. Portfolio Story Arc

Your three projects now tell a clear, progressive story:

```
Project 1: RAG + RBAC + Guardrails
  → Foundation: retrieval, access control, safety
  → "I can build intelligent knowledge systems"

Project 2: Multi-Agent Incident Response
  → Level up: agent orchestration, self-healing loops, production monitoring
  → "I can build autonomous multi-agent systems"

Project 3: Voice Agent for Healthcare
  → Mastery: real-time voice pipeline + agents + RAG + domain application
  → "I can build production-grade AI systems that handle real users"
```

Each project reuses and extends skills from the previous one.
This is exactly the kind of growth trajectory hiring managers look for.
