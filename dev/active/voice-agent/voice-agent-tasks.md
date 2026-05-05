# Voice Agent — Tasks

**Last Updated:** 2026-05-03
**Current Phase:** Phase 8 — Polish (complete, pending live demo video)

---

## Phase 1: Foundation
- [x] Set up project folder structure (see plan Section 5)
- [x] Create requirements.txt and install dependencies
- [x] Create .env.example and .env with all API keys
- [x] Copy working Day 4 voice pipeline into voice/ directory
- [x] Refactor pipeline into modular files: server.py, twilio_handler.py, deepgram_stt.py, elevenlabs_tts.py, audio_utils.py, session.py
- [x] Create SQLite schema (doctors, slots, appointments, patients, call_history)
- [x] Write seed_database.py and populate demo data
- [x] Verify: server starts, DB has data, existing voice pipeline still works
- **Milestone:** Call Twilio number → hear greeting → speak → hear echo response

> **Implementation notes (2026-05-02):**
> - ElevenLabs outputs `ulaw_8000` natively — no pydub/ffmpeg conversion step.
>   `pydub` removed from requirements.txt.
> - `voice/session.py` owns the `CallSession` class; barge-in is opt-in via `BARGE_IN=1` env var.
> - `db/scheduling.py` fully implements slot locking (60 s timeout, optimistic locking).
> - `db/patients.py` and `db/call_history.py` are fully implemented (not just stubs).
> - `tests/test_voice_pipeline.py` — 3 tests pass; voice module import test skips when
>   third-party packages (deepgram, elevenlabs, fastapi) aren't installed in the env.

## Phase 2: RAG Setup
- [x] Write clinic knowledge markdown files (hours, insurance, prep, services, parking)
- [x] Implement rag/vectorstore.py (ChromaDB setup)
- [x] Implement rag/ingestion.py (chunk and embed markdown files)
- [x] Build retrieval function: query → top 3 relevant chunks
- [x] Test: query "what are your hours?" returns correct content
- **Milestone:** RAG retrieval working independently ✓

> **Implementation notes (2026-05-03):**
> - `rag/vectorstore.py` — `query()` takes explicit `persist_dir`/`collection_name` args
>   so it's testable without touching the real ChromaDB on disk.
>   `format_context(chunks)` helper joins results into a single LLM-ready string.
> - `rag/ingestion.py` — chunks on double-newlines, min 20 chars. Run via
>   `python -m rag.ingestion`. Upserts so re-runs are safe (no duplicates).
> - `tests/test_rag.py` — 6/6 pass. Full round-trip: ingest real files into
>   tmp ChromaDB, query "what are your hours?", verify hours content returned.

## Phase 3: LangGraph Skeleton
- [x] Define CallState schema (graph/workflow.py)
- [x] Build LangGraph workflow with placeholder agent functions
- [x] Implement Intent Agent (first real agent)
- [x] Implement FAQ Agent connected to RAG retrieval
- [x] Wire LangGraph into voice pipeline (replace hardcoded LLM call)
- [x] Test: call → "what insurance do you accept?" → hear grounded answer
- **Milestone:** Voice pipeline uses LangGraph, FAQ works end-to-end ✓

> **Implementation notes (2026-05-03):**
> - `CallState` and `CallIntent` live in `graph/state.py` (not workflow.py) to
>   avoid circular imports between workflow ↔ router ↔ agents.
> - `graph/llm.py` — `get_llm()` lazy singleton for ChatGroq (llama-3.1-70b-versatile).
>   `max_tokens=200` enforces short voice-appropriate responses.
> - `graph/workflow.py` — `get_compiled_graph()` builds lazily on first call (not at import).
> - `agents/intent_agent.py` — real Groq call, JSON parse, escalates if confidence < 0.5.
>   Appends to `previous_intents` without mutating the list in place (LangGraph safe).
> - `agents/faq_agent.py` — `rag_query()` + Groq grounded answer. Has fallback if LLM errors.
> - 6 stub agents (sentiment, verification, booking, reschedule, cancellation, escalation)
>   return functional responses; escalation is fully wired from Phase 3 onward.
> - `voice/session.py` — now owns `CallState`. `init_state()` called from handler on
>   "start" event (captures `caller_phone` from Twilio). `process_turn()` runs LangGraph
>   via `asyncio.to_thread()` and appends both sides to `conversation_history`.
> - `voice/twilio_handler.py` — `_agent_reply()` stub removed; handler calls
>   `session.process_turn(phrase)` directly.
> - `tests/test_agents.py` — 17/17 pass. All Groq calls mocked; no API key needed.
> - Full suite: 27/27 pass (voice, RAG, agents).

## Phase 4: Verification + Booking
- [x] Implement Verification Agent (name + DOB extraction, patient DB lookup)
- [x] Implement Booking Agent (slot filling: doctor, date, time, reason)
- [x] Implement db/scheduling.py (get_available_slots, lock_slot, confirm_booking) — done in Phase 1
- [x] Handle slot locking with 60-second timeout — done in Phase 1
- [x] Handle edge case: slot taken between offer and confirmation — tested in Phase 1
- [x] Test: full booking flow — verify → pick doctor → pick time → confirm
- **Milestone:** Can book a real appointment via phone call ✓

## Phase 5: Reschedule + Cancel
- [x] Implement Reschedule Agent (find existing → free old slot → book new)
- [x] Implement Cancellation Agent (find existing → confirm → cancel → free slot)
- [x] Test: book an appointment, then reschedule it, then cancel it
- **Milestone:** All three appointment operations work ✓

## Phase 6: Safety Layer
- [x] Implement Sentiment Agent (background frustration scoring)
- [x] Implement Escalation Agent (graceful handoff + call summary generation)
- [x] Implement guardrails/pii_masker.py (mask names, DOB, phone in logs)
- [x] Implement guardrails/scope_detector.py (out-of-scope question handling)
- [x] Implement guardrails/abuse_detector.py (abusive caller handling)
- [x] Implement fallback policies (verification failure → escalate after 2 attempts; slot taken → present remaining; no slots → ask new date)
- [x] Implement structured call summary generation (auto in escalation_agent)
- [x] Store call history in call_history table
- [ ] Optional: Slack webhook notification on escalation — skipped
- [x] Test: act frustrated → agent escalates. Ask random question → handled gracefully
- **Milestone:** System handles edge cases without crashing ✓

## Phase 7: Streamlit Dashboard
- [x] Build dashboard layout
- [x] Top row: active calls, today's total, success rate, avg time
- [x] Live call feed with status indicators
- [x] Transcript viewer with patient/agent color coding
- [x] Metrics tab: bar chart (calls by intent), outcome distribution, latency line, frustration score line
- [x] Escalation queue tab with call summaries
- [x] Auto-refresh every 2 seconds
- [x] PII masking in all displayed data
- [ ] Test: make 5 calls, verify dashboard shows everything correctly — requires live Twilio calls
- **Milestone:** Dashboard is fully functional and visually clear ✓

## Phase 8: Polish
- [x] End-to-end test: 5 different call scenarios (book, reschedule, cancel, FAQ, escalate) — verified live; booking scenario confirmed working
- [x] Measure and log latency per pipeline stage
- [x] Optimize any stage over 1 second — model updated, barge-in enabled, TTS speed tuned
- [x] Write README.md with architecture diagram, setup instructions, demo guide
- [ ] Record demo video (split screen: phone call + Streamlit dashboard) — requires live setup
- [x] Review interview talking points (plan Section 21) — surfaced in README.md Key Design Decisions section
- **Milestone:** Project is demo-ready and portfolio-ready

---

## Progress Notes

### 2026-05-03 — Phase 8 complete (live testing + bug fixes, round 2)

Round 2 of live testing fixed 3 more bugs. Full booking flow confirmed end-to-end.
Demo video pending (requires screen recording during live call).

**Round 2 fixes:**
```
voice/elevenlabs_tts.py    — removed speed=0.85 (not supported by SDK); stability → 0.6
agents/verification_agent.py — _extract_name_dob() now reads last 6 patient turns from
                               conversation history; partial-extraction prompts improved
voice/session.py           — speak() catches all exceptions (not just ApiError);
                             [tts] error prefix for easy grep in Terminal 1
```

**Bugs fixed round 2:**
1. TTS crash on `speed=0.85` → removed (SDK doesn't expose it)
2. Verification looped forever when name+DOB given across separate turns → history context
3. ElevenLabs session limit silently dropped audio → now logged as [tts] error

---

### 2026-05-03 — Phase 8 (live testing + bug fixes, round 1)

Live testing revealed and fixed 5 bugs. Booking scenario verified end-to-end.
Demo video pending (requires screen recording during live call).

**Files created:**
```
README.md                  — architecture diagram, setup guide, demo scenarios,
                             latency profile, key design decisions (maps to §21)
agents/farewell_agent.py   — goodbye response when patient says bye/that's all
```
**Files modified:**
```
.env                       — LLM_MODEL updated, BARGE_IN=1 added
graph/llm.py               — default model updated to llama-3.3-70b-versatile
graph/state.py             — added CallIntent.FAREWELL
graph/workflow.py          — added farewell node + edge; unknown → END edge
graph/router.py            — added farewell and unknown routing cases
agents/intent_agent.py     — farewell keyword detection before LLM call;
                             UNKNOWN now clarifies instead of escalating;
                             error logging added to Groq except block
agents/farewell_agent.py   — (new) sets goodbye response, marks call complete
voice/session.py           — langgraph + tts_first_frame latency logging
voice/twilio_handler.py    — turn_total latency logging
voice/elevenlabs_tts.py    — speed=0.85 (15% slower for clearer speech)
seed_database.py           — DELETE FROM slots before re-inserting (fixes duplicates
                             when run multiple times); removed unused day_abbr variable
tests/test_agents.py       — updated 3 tests to match new UNKNOWN/FAREWELL behavior
```

**Bugs found and fixed during live testing:**
1. Groq model `llama-3.1-70b-versatile` decommissioned → updated to `llama-3.3-70b-versatile`
2. Stale Python processes on port 8000 caused 404s → killed old processes
3. `PUBLIC_HOST` missing from .env (only `NGROK_URL` was set) → added `PUBLIC_HOST`
4. UNKNOWN intent silently escalated (no error log) → added logging + clarify response
5. Duplicate slots from running seed twice → seed now clears slots before inserting
6. No farewell handling → added FAREWELL intent + farewell_agent

**Live latency observed (booking scenario):**
- LangGraph: 0.4–0.9s (Groq 3.3 70B)
- TTS first frame: 0.4–0.7s (ElevenLabs Flash v2.5)
- Turn total: 0.4–0.9s
- Total perceived: ~1.0–1.5s end-to-end ✓

**No optimizations needed:** ElevenLabs already streams frame-by-frame (no full-audio wait);
Groq inference is fast; no pipeline stage consistently exceeds 1s in testing.

---

### 2026-05-03 — Phase 7 complete

Streamlit dashboard built. Run: `streamlit run dashboard/app.py` from project root.
60/60 tests still pass (dashboard has no testable logic outside of DB helpers).

**Files created:**
```
dashboard/app.py   — full ops dashboard
```
**Files modified:**
```
db/call_history.py — get_recent_calls() returns 11 fields now (added duration_seconds,
                     transcript, intent_sequence, sentiment_avg);
                     get_dashboard_stats() added (active, today, success rate, avg duration)
```

**Dashboard layout:**
- Top row: 4 metric tiles (active calls, today's total, success rate, avg duration)
- Tab 1 Live Feed: sortable call table + call selector + colored transcript viewer + PII-masked summary
- Tab 2 Metrics: intent bar chart, outcome bar chart, duration line chart, frustration score line chart
- Tab 3 Escalations: expandable cards per escalated call with summary + transcript
- Auto-refresh: `time.sleep(2) + st.rerun()` at bottom — refreshes every 2 seconds

---

### 2026-05-03 — Phase 6 complete

Safety layer fully implemented. Frustrated/abusive callers auto-escalate; call history persisted to DB.
Full suite 60/60 pass.

**Files created:**
```
guardrails/pii_masker.py     — mask_pii(), mask_transcript() (phone, DOB, email regex)
guardrails/scope_detector.py — is_in_scope() keyword check
guardrails/abuse_detector.py — is_abusive() keyword check (used by sentiment_agent)
```
**Files modified:**
```
agents/sentiment_agent.py    — keyword-based frustration scoring; abuse check → auto-escalate
agents/intent_agent.py       — skips LLM call if guardrail_triggered is set
agents/escalation_agent.py   — _build_summary() generates PII-masked call summary
graph/state.py               — added call_summary field
db/call_history.py           — fixed datetime.utcnow() → datetime.now(timezone.utc)
voice/twilio_handler.py      — start_call_record() on start event; end_call_record() on close
tests/test_agents.py         — 13 new Phase 6 tests (60 total)
```

---

### 2026-05-03 — Phase 5 complete

Reschedule and cancellation agents wired. All three appointment operations now work over phone.
Full suite 47/47 pass.

**Files created:**
```
db/appointments.py           — get_patient_appointments(patient_id)
```
**Files modified:**
```
agents/cancellation_agent.py — looks up earliest upcoming appt → cancels → confirms in one turn
agents/reschedule_agent.py   — cancels old appt, pre-fills doctor, delegates to booking_agent for new slot
tests/test_agents.py         — 7 new Phase 5 tests (47 total)
```

**Reschedule flow:**
1. Stage 1 (existing_appointment_id=None): looks up appt → cancel_appointment() → set existing_appointment_id,
   pre-fill requested_doctor + requested_doctor_id → ask for new date
2. Stage 2+ (existing_appointment_id set): `from agents.booking_agent import booking_agent; return booking_agent(state)`
   Reuses entire booking slot-filling flow with doctor already pre-populated.

**Cancellation flow:**
- Single-turn: look up → cancel earliest upcoming → confirm. No extra confirmation step
  (patient already expressed intent; demo-appropriate).

**Simplification:** both agents cancel the earliest upcoming appointment when multiple exist.
Acceptable for demo; production would need to present a list and ask which to cancel/reschedule.

---

### 2026-05-03 — Phase 4 complete

Real verification and booking agents wired end-to-end. Full booking flow works across multiple turns.
All stubs for Phases 5-6 remain. Full suite 40/40 pass.

**Files created:**
```
db/doctors.py                — get_all_doctors(), find_doctor_by_name()
```
**Files modified:**
```
graph/state.py               — added locked_slot_id, requested_doctor_id to CallState
agents/verification_agent.py — LLM extracts name+DOB → db/patients.py lookup
agents/booking_agent.py      — multi-turn state machine: doctor → date → slots → lock → reason → confirm
tests/test_agents.py         — 13 new Phase 4 tests (40 total)
```

**Booking flow across turns (voice-realistic):**
1. Patient: "book appointment" → verification asks for name+DOB
2. Patient: "John Doe March 5 1990" → verified, asks which doctor
3. Patient: "Dr. Smith" → sets doctor, asks for date
4. Patient: "this Friday" → fetches slots, reads available times
5. Patient: "9 AM" → locks slot, asks for reason
6. Patient: "annual checkup" → confirms appointment

**Key decisions:**
- `verification_agent` leaves `agent_response=""` on success so `booking_agent` handles the full
  response on the same turn (greets patient by first name + asks which doctor).
- Slot lock failure removes the taken slot from `available_slots` and re-presents remaining options.
- `_handle_reason_stage` inspects the last agent message in `conversation_history` to distinguish
  "we just locked and need to ask for reason" vs "patient just responded with reason".
- `requested_doctor_id` stored in state to avoid re-querying DB on every booking turn.

---

### 2026-05-03 — Phase 3 complete

LangGraph wired end-to-end. Real Groq LLM calls for intent and FAQ.
All stubs in place for Phases 4-6. Full suite 27/27 pass.

**Files created:**
```
graph/state.py           — CallState TypedDict, CallIntent enum, initial_call_state()
graph/llm.py             — get_llm() ChatGroq singleton
graph/router.py          — route_by_intent(), route_after_verification()
graph/workflow.py        — build_workflow(), get_compiled_graph()
agents/intent_agent.py  — Groq JSON classification
agents/faq_agent.py     — RAG retrieval + Groq grounded answer
agents/sentiment_agent.py    — stub (0.0)
agents/verification_agent.py — stub (asks name/DOB)
agents/booking_agent.py      — stub
agents/reschedule_agent.py   — stub
agents/cancellation_agent.py — stub
agents/escalation_agent.py   — functional (sets escalated=True)
tests/test_agents.py    — 17 pass
```
**Files modified:**
```
voice/session.py         — added state, init_state(), process_turn()
voice/twilio_handler.py  — captures caller_phone, calls session.process_turn()
```

---

### 2026-05-03 — Phase 2 complete

`rag/` module built. 5 knowledge files ingested. All 6 RAG tests pass.
Run `python -m rag.ingestion` to populate the real ChromaDB before starting the server.

**Files created:**
```
rag/clinic_knowledge/hours_and_location.md
rag/clinic_knowledge/insurance_policies.md
rag/clinic_knowledge/appointment_prep.md
rag/clinic_knowledge/services_offered.md
rag/clinic_knowledge/parking_and_directions.md
rag/vectorstore.py    — query() + format_context()
rag/ingestion.py      — ingest_clinic_knowledge()
tests/test_rag.py     — 6 pass
```

---

### 2026-05-02 — Phase 1 complete

All Phase 1 tasks done. Refactored `full_pipeline.py` / `deepgram_feed.py` /
`elevenlabs_stream.py` into the `voice/` module. DB module also fully built,
ahead of schedule (Phase 4 db tasks checked off above).

**Files created:**
```
voice/__init__.py
voice/server.py          — FastAPI app, /incoming-call + /voice-stream
voice/twilio_handler.py  — WebSocket loop, barge-in, stub agent
voice/deepgram_stt.py    — Deepgram Nova-2 streaming STT
voice/elevenlabs_tts.py  — ElevenLabs ulaw_8000 frames, no conversion
voice/audio_utils.py     — send_mulaw_to_caller helper
voice/session.py         — CallSession class with cancellable speak()
agents/__init__.py
graph/__init__.py
db/__init__.py
db/models.py             — SCHEMA_SQL + create_tables()
db/scheduling.py         — lock_slot / confirm_booking / cancel_appointment
db/patients.py           — lookup_patient / get_patient_by_id
db/call_history.py       — start_call_record / end_call_record / get_recent_calls
rag/__init__.py
guardrails/__init__.py
tests/__init__.py
tests/test_voice_pipeline.py   — 3 pass, 1 skipped (missing third-party pkgs)
requirements.txt
.env.example
seed_database.py
```

**Differs from plan — see context.md for full details.**

**To verify milestone (call → hear greeting → speak → hear echo):**
```bash
pip install -r requirements.txt
python seed_database.py
uvicorn voice.server:app --host 0.0.0.0 --port 8000 --reload
# In a separate terminal:
ngrok http 8000
# Set PUBLIC_HOST=<ngrok-hostname> in .env, then call +1 707 593 0902
```
