# Voice Agent — Tasks

**Last Updated:** 2026-05-06
**Current Phase:** Complete - final live demo validated and repo cleanup finished

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
- [x] Optional: Slack webhook notification on escalation — implemented by Codex with masked summaries
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
- [x] Test: make 5 calls, verify dashboard shows everything correctly — final live validation complete
- **Milestone:** Dashboard is fully functional and visually clear ✓

## Phase 8: Polish
- [x] End-to-end test: 5 different call scenarios (book, reschedule, cancel, FAQ, escalate) — final live validation complete
- [x] Measure and log latency per pipeline stage
- [x] Optimize any stage over 1 second — model updated, barge-in enabled, TTS speed tuned
- [x] Write README.md with architecture diagram, setup instructions, demo guide — final portfolio README complete
- [x] Record/demo readiness pass (phone call + Streamlit dashboard) — final live scenarios validated
- [x] Review interview talking points (plan Section 21) — surfaced in README.md Key Design Decisions section
- **Milestone:** Project is demo-ready and portfolio-ready

---

## Progress Notes

> Current status is the final completion snapshot above. Older "remaining" or
> "pending" notes below are historical and were superseded by later validation.

### 2026-05-06 - Final README and archive cleanup

Completed the final documentation and conservative cleanup pass.

**Changes:**
- Rewrote `README.md` as the final architecture, setup, demo, safety, and validation overview.
- Archived legacy Day 4 prototype scripts under `dev/archive/legacy-day4-pipeline/`.
- Added an archive README explaining that the modular `voice/` server supersedes those scripts.
- Updated active dev docs to mark the project complete and demo validated.

**Final status:**
- Live validation is complete for booking, reschedule, cancellation confirmation, FAQ, escalation, dashboard masking/status display, and barge-in.
- Automated status remains `pytest tests/ -v` -> 128 passed, 2 deprecation warnings.
- No live Twilio rerun is needed for this cleanup pass.

### 2026-05-06 - Inline date/time slot reservation

Improved booking and reschedule date collection so callers can combine date and
time in one response.

**Fixes:**
- When a date-stage utterance includes a clear offered time, such as
  "tomorrow at 9 AM", booking now locks that matching slot immediately and asks
  for the visit reason.
- Doctor-stage utterances that include date and time, such as
  "Dr. Chen tomorrow at 9 AM", use the same fast path.
- Reschedule inherits the same behavior for replacement appointments while still
  keeping the old appointment until the new booking is confirmed.
- If the requested time is unavailable or ambiguous, the agent still reads the
  available choices instead of guessing.

**Tests:**
- `pytest tests/test_agents.py -q` -> 112 passed, 2 deprecation warnings.
- `pytest tests/ -v` -> 128 passed, 2 deprecation warnings.

### 2026-05-06 - Appointment workflow state reset

Fixed stale appointment workflow state leaking across long same-call demos.

**Fixes:**
- Added explicit active appointment workflow state plus latest-confirmed
  appointment memory on `CallState`.
- Fresh booking/reschedule/cancel intents now clear stale slot-filling and
  pending existing-appointment fields outside active prompts.
- Unconfirmed locked slots are released when switching workflows.
- Booking records the latest confirmed appointment; same-call reschedule/cancel
  target that latest appointment before falling back to earliest upcoming DB
  lookup.
- Reschedule keeps the old appointment until the replacement booking succeeds,
  then clears pending old-appointment state and updates latest-confirmed details.
- Cancellation "no" clears only pending cancellation state; cancellation "yes"
  clears matching latest-confirmed state after the DB cancellation succeeds.

**Tests:**
- `pytest tests/test_agents.py -q` -> 109 passed, 2 deprecation warnings.
- `pytest tests/ -v` -> 125 passed, 2 deprecation warnings.

### 2026-05-06 - Final live validation and TTS quota note

Reviewed the latest live combo call after the booking selection reliability patch.

**Confirmed working:**
- Booking recognized Dr. Emily Johnson cleanly and selected the 12:00 PM slot.
- FAQ follow-ups for insurance, Sunday hours, location, and an unavailable detail
  answered correctly and stayed concise.
- Reschedule reached the expected workflow and confirmed the replacement appointment.
- Caller phone stayed masked, appointment dates stayed visible, and barge-in fired.

**Only issue:**
- ElevenLabs returned `quota_exceeded` near the end of the call. This is an
  operational account-credit limit, not an app failure.

**Remaining before recording:**
- Restore enough ElevenLabs credits, shorten the recorded script, or switch to a
  configured TTS fallback before recording the demo.

### 2026-05-06 - Booking selection reliability follow-up

Live booking still showed one repeated doctor prompt and occasional time/date
sensitivity, so the deterministic selection layer was broadened.

**Fixes:**
- If the booking LLM returns a partial doctor name such as `Dr. Smith`, booking now
  resolves it through deterministic matching against the current doctor list before
  falling back to DB substring lookup.
- Doctor selection now accepts explicit option phrases such as `the first one` and
  `number two`.
- Slot selection now accepts option phrases such as `first`, `second`, `number two`,
  `last`, `earliest`, and `latest`.
- Slot selection now maps `noon` and `midday` to a 12:00 PM offered slot.
- Bare cardinal words like `one` are not treated as option indexes unless the caller
  says `number one`, `option one`, or `choice one`, avoiding ambiguity with times.

**Tests:**
- `pytest tests/test_agents.py -q` -> 103 passed, 2 deprecation warnings.
- `pytest tests/ -v` -> 119 passed, 2 deprecation warnings.

### 2026-05-06 - Deterministic doctor-name matching

Implemented deterministic doctor-name matching before the booking doctor LLM.

**Fixes:**
- Booking now matches common doctor responses directly, including full name,
  first+last, unique last name, and unique first name. Demo examples covered:
  `Dr Patel`, `Raj Patel`, `Patel`, `Raj`, `Doctor Chen`, and `Emily`.
- Ambiguous shared first or last names do not guess; they fall back to the existing
  LLM extractor.
- The deterministic path sets `requested_doctor` and `requested_doctor_id` directly,
  avoiding an extra repeated doctor prompt for clear demo doctor names.

**Tests:**
- `pytest tests/test_agents.py -q` -> 92 passed, 2 deprecation warnings.
- `pytest tests/ -v` -> 108 passed, 2 deprecation warnings.

**Demo status:**
- Streamlit FAQ status was confirmed as `FAQ Answered`.
- Remaining step is demo recording.

### 2026-05-06 - Live validation after demo polish

Reviewed the latest sanitized live logs after the FAQ/dashboard/routing polish.

**Confirmed working:**
- Booking completed with verification, doctor selection, date selection, slot lock,
  visit reason, confirmation, and farewell.
- FAQ calls stayed concise for insurance, Saturday hours, unavailable details, and
  location/directions. The unavailable detail used the front-desk fallback.
- Reschedule kept the old appointment until the replacement was booked, then cancelled
  the previous appointment.
- Cancellation required confirmation before cancelling.
- Escalation reached the front-desk handoff response.
- Caller phone remained masked as `[PHONE]`, appointment dates stayed visible, and
  barge-in fired during live calls.

**Remaining before recording:**
- Streamlit FAQ status was later confirmed as `FAQ Answered`.
- Deterministic doctor-name matching was later implemented to remove the repeated
  doctor-prompt risk.

### 2026-05-06 - Demo polish implementation

Implemented the final demo-polish fixes from the plan.

**Fixes:**
- FAQ-only answers now set `call_outcome="faq_answered"` when no prior appointment
  or escalation outcome exists.
- Streamlit status mapping now labels `faq_answered` as `FAQ Answered`; `completed`
  remains a neutral farewell-only outcome label.
- Verified booking/reschedule doctor-selection turns now stay in the active
  appointment workflow before `requested_doctor` is populated, without calling
  the intent LLM.
- FAQ answers are now prompted as 1-2 short phone-friendly sentences; unavailable
  answers use only the front-desk fallback sentence.

**Tests:**
- `pytest tests/test_agents.py -q` -> 82 passed, 2 deprecation warnings.
- `pytest tests/ -v` -> 98 passed, 2 deprecation warnings.

**Still open:**
- Manual Twilio/ngrok validation for one short FAQ call, one booking doctor-selection
  call, and final dashboard masking/status review before recording the demo video.

### 2026-05-06 - Demo polish plan

Polishing the final live-demo concerns with scoped fixes.

**Planned fixes:**
- Treat FAQ-only calls as a first-class `faq_answered` outcome so Streamlit live
  feed and charts do not render them as `Unknown`.
- Tighten verified appointment-workflow routing so answers to the doctor-selection
  prompt stay in booking or reschedule before `requested_doctor` is populated.
- Constrain FAQ responses to 1-2 short phone-friendly sentences and keep the
  unavailable-answer fallback to the front-desk handoff sentence only.

**Validation planned:**
- Add focused unit coverage for FAQ outcomes, dashboard status mapping, active
  doctor-selection routing, and concise markdown FAQ behavior.
- Run `pytest tests/test_agents.py -q` and `pytest tests/ -v`.

### 2026-05-06 - FAQ demo cleanup and deterministic slot parsing

Implemented the remaining code cleanup from the caveats plan.

**Fixes:**
- Added `FAQ_RETRIEVAL_MODE=markdown|chroma`, defaulting to `markdown`.
  In markdown mode, FAQ calls skip Chroma entirely and answer from the clinic
  markdown knowledge files, avoiding the noisy live `FAQ RAG error` path.
- Kept Chroma retrieval available with `FAQ_RETRIEVAL_MODE=chroma`; Chroma
  exceptions still fall back to markdown context.
- Added deterministic offered-slot parsing before the booking LLM extractor.
  It maps common forms like `10`, `10 AM`, `ten`, `ten AM`, `ten o'clock`,
  and `the 10 o'clock one` to the matching displayed slot, while rejecting
  times not in the offered list.
- Documented `FAQ_RETRIEVAL_MODE` in `.env.example` and README.

**Tests:**
- `pytest tests/test_agents.py -q` -> 73 passed, 2 deprecation warnings.
- `pytest tests/ -v` -> 89 passed, 2 deprecation warnings.

**Still open:**
- Manual Twilio/ngrok validation for the five live scenarios and Streamlit dashboard masking.
- Demo video recording after the live pass is clean.

### 2026-05-05 - Latest live validation

Reviewed the latest sanitized live logs after the active workflow routing fix.

**Confirmed working:**
- Caller phone now appears in logs as masked `from=[PHONE]`, not `from=unknown`.
- Booking flow completed with verification, doctor selection, date selection, slot lock,
  visit reason, and confirmation.
- Appointment dates remain visible in masked agent logs, e.g. booking and reschedule
  confirmations show appointment dates instead of `[DOB]`.
- Reschedule now completes correctly: the final response states that the previous
  appointment was cancelled and the new appointment was confirmed.
- Barge-in continues to work and cancels outbound TTS during interruptions.
- Cancellation confirmation and escalation were validated in the previous live pass.

**Remaining caveats:**
- Slot selection occasionally required repeated attempts before the time was recognized.
  The workflow stayed in the correct booking/reschedule state; this is now an STT/time
  parsing sensitivity issue rather than a routing bug. For demo, say times clearly like
  "10 AM" or "ten o'clock AM".
- FAQ still logs ChromaDB `FAQ RAG error` and uses markdown fallback context. Calls
  continue safely, but the log noise should be cleaned up before a polished demo if time
  allows.
- Dashboard live-call display and demo recording remain manual final steps.

**Tests:**
- No code changes in this note. Last full run: `pytest tests/ -v` -> 80 passed, 2 deprecation warnings.

### 2026-05-05 - Active workflow routing fix

A later live pass showed all major flows were mostly working, but revealed a real
reschedule correctness issue. During the reschedule slot-selection turn, the LLM intent
classifier flipped from `reschedule` to `booking`. That booked the new appointment but
skipped `reschedule_agent`, so the old appointment was not cancelled. A later cancellation
call found both appointments, confirming the reschedule had become an add-on booking.

The booking flow showed a related symptom: while choosing a time, one slot-selection
utterance was classified as `reschedule`, producing a brief "no upcoming appointments"
response before recovering.

**Fixes:**
- `intent_agent` now detects active transactional prompts such as "which time works",
  "available times", "what date", "which doctor", and "reason for your visit".
- If a booking is in progress, responses to those prompts route to `booking` without
  asking the LLM classifier.
- If a reschedule is in progress, responses to those prompts route to `reschedule`
  without asking the LLM classifier, allowing `reschedule_agent` to cancel the old
  appointment after the new booking is confirmed.
- Added regression tests for active booking and active reschedule slot prompts being
  kept in the correct workflow.

**Tests:**
- `pytest tests/ -v` -> 80 passed, 2 deprecation warnings.

**Live validation next:**
- Restart uvicorn and retry reschedule. The final response should explicitly say the
  previous appointment was cancelled and the new appointment is confirmed.

### 2026-05-05 - Live validation follow-up

Reviewed sanitized live logs for cancellation, booking, cancellation-confirmation, and
escalation calls.

**Live results:**
- Barge-in is now working during FAQ and booking prompts. Logs show
  `[barge-in] caller speech detected; cancelling TTS`, followed by the next user turn
  being processed.
- Booking successfully verified the caller, collected doctor/date/time/reason, locked a
  slot, and confirmed the appointment.
- Cancellation confirmation now follows the safer flow: identify the appointment, ask
  whether to cancel it, then cancel after an affirmative response.
- Escalation routes to the front desk handoff response.
- A cancellation attempt with no matching verified record or no upcoming appointments
  returns the expected fallback instead of making a destructive change.

**Issues found and fixed:**
- An `unknown` intent at confidence `0.5` reused the previous agent response because the
  fallback only handled confidence below `0.5`. `intent_agent` now sets a fresh unknown
  fallback for any `unknown` intent and routes "no" after "anything else?" to farewell.
- Appointment dates in agent logs/dashboard were masked as `[DOB]` because the PII masker
  treated every ISO date as a DOB. `mask_pii()` now masks dates only when they appear in
  DOB/birthday contexts, preserving appointment dates such as booking confirmations.
- Live call starts still logged `from=unknown`. `/incoming-call` now passes Twilio's
  caller number into the Media Stream as a custom parameter, and the stream handler reads
  it from the `start` event.

**Tests:**
- `pytest tests/ -v` -> 78 passed, 2 deprecation warnings.

**Still open:**
- Restart uvicorn and verify the next live call logs `from=[PHONE]` instead of
  `from=unknown`.
- ChromaDB still logs `FAQ RAG error` during live FAQ. Calls continue using markdown
  fallback context, but the persistent-client error should be cleaned up before the final
  demo if time allows.
- Dashboard live-call display and demo recording still need final manual validation.

### 2026-05-05 - Cancellation confirmation fix

Live cancellation testing showed the cancellation agent was too destructive: after
verification, every `cancel` intent immediately cancelled the earliest upcoming
appointment. In one call, that allowed two separate appointments to be cancelled.

**Fixes:**
- `agents/cancellation_agent.py` now identifies the earliest upcoming appointment and
  asks for confirmation before calling `cancel_appointment()`.
- A pending cancellation accepts clear yes/no responses; negative responses leave the
  appointment unchanged and clear the pending cancellation state.
- `agents/intent_agent.py` routes pending cancellation yes/no confirmations without an
  LLM call so short answers like "yes" do not fall through as unknown.
- `agents/reschedule_agent.py` ignores appointment state left over from a completed
  cancellation, preventing a later reschedule intent from incorrectly entering booking.
- Added regression tests for confirm-before-cancel, negative confirmation, pending
  confirmation intent routing, and cancelled-state reschedule handling.

**Tests:**
- `pytest tests/ -v` -> 75 passed, 2 deprecation warnings.

**Live validation next:**
- Restart uvicorn before retrying cancellation.
- Expected flow: ask to cancel, verify identity, agent says it found one appointment and
  asks if it should cancel it, caller says yes, then exactly that appointment is cancelled.

### 2026-05-05 - Twilio buffer-aware barge-in fix

Live FAQ testing showed the local TTS task could finish before the caller interrupted,
while Twilio continued playing already-buffered audio. That made the agent appear to
finish its whole answer before listening.

**Fixes:**
- `voice/session.py` now keeps playback active until Twilio returns the matching TTS
  `mark` event instead of clearing `speaking` when local frame sending finishes.
- `voice/audio_utils.py` now supports Twilio `mark` and `clear` messages.
- `voice/twilio_handler.py` handles incoming `mark` events and sends `clear` when
  barge-in speech is detected or a finalized new user turn starts.
- Barge-in detection no longer requires the local `speak_task` to still be running,
  because Twilio may still be playing buffered audio after that task completes.
- Added regression tests for Twilio mark-based playback tracking and clear-on-cancel.

**Tests:**
- `pytest tests/ -v` -> 71 passed, 2 deprecation warnings.

**Live validation next:**
- Restart uvicorn, call again with `BARGE_IN=1`, and confirm startup logs include
  `[barge-in] enabled rms_threshold=... speech_frames=... silence_frames=...`.
- Interrupt during TTS and confirm `[barge-in] caller speech detected; cancelling TTS`
  appears and the spoken audio stops promptly.

### 2026-05-05 - Barge-in VAD fix

Live testing confirmed TTS audio was audible, but the agent did not stop speaking when the
caller interrupted. The previous no-audio fix had disabled raw-media cancellation entirely.

**Fixes:**
- Added `voice/barge_in.py`, a lightweight G.711 mulaw RMS detector.
- With `BARGE_IN=1`, `voice/twilio_handler.py` now cancels TTS only after sustained inbound
  speech frames, not on silence/noise.
- Added tunables in `.env.example`: `BARGE_IN_RMS_THRESHOLD`, `BARGE_IN_SPEECH_FRAMES`,
  and `BARGE_IN_SILENCE_FRAMES`.
- Added tests for silence rejection and sustained speech detection.

**Tests:**
- `pytest tests/ -v` -> 69 passed, 2 deprecation warnings.

**Live validation next:**
- Restart uvicorn and interrupt the agent with a clear sentence while it is speaking.
- Confirm the server logs `[barge-in] caller speech detected; cancelling TTS`.
- If it does not trigger, lower `BARGE_IN_RMS_THRESHOLD` from `900` to `700` and retry.

---

### 2026-05-05 - Live FAQ crash hardening

Live FAQ testing triggered a ChromaDB Rust/PyO3 panic:
`range start index 10 out of range for slice of length 9`. The panic propagated through
LangGraph and killed the Twilio WebSocket because it was not a normal `Exception`.

**Fixes:**
- `faq_agent` catches non-system `BaseException` from RAG retrieval and logs
  `FAQ RAG error: ...` instead of crashing.
- FAQ now falls back to direct markdown knowledge-base context if ChromaDB retrieval fails.
- `CallSession.process_turn()` catches non-system `BaseException` from LangGraph/native
  dependencies and returns a technical fallback instead of taking down the WebSocket.
- Added regression tests for FAQ RAG native-panic handling and session-level native-panic
  handling.

**Tests:**
- `pytest tests/ -v` -> 68 passed, 2 deprecation warnings.

**Live validation next:**
- Restart uvicorn and retry FAQ. If ChromaDB still logs a RAG error, the call should continue
  and answer using markdown fallback context.

---

### 2026-05-05 - Live TTS/dashboard fix

First live booking call after replacing the Groq key reached LangGraph and booked an
appointment, but the caller could not hear the agent. Server logs had no
`[latency] tts_first_frame=...`, which pointed to TTS being cancelled before the first
audio frame.

**Fixes:**
- `BARGE_IN=1` no longer cancels TTS on every raw Twilio media packet; raw media includes
  silence/noise and was muting the agent immediately.
- With barge-in enabled, TTS runs in the background and is only cancelled when a finalized
  new utterance is processed.
- `voice/session.py` now logs when TTS is skipped for a missing stream SID, cancelled, or
  completes without sending frames.
- Start-event handling now falls back to top-level `streamSid` if Twilio does not include
  it inside the `start` object.
- Dashboard transcript cards now set explicit dark text so light cards remain readable in
  Streamlit dark mode.

**Tests:**
- `pytest tests/ -v` -> 66 passed, 2 deprecation warnings.

**Live validation next:**
- Restart uvicorn and retry one call. Confirm the server logs `[latency] tts_first_frame=...`
  after each agent response and the caller hears audio.

---

### 2026-05-05 - Codex finishing pass

Codex implemented the remaining non-live finishing items from the handoff plan.
Root `AGENTS.md` was not changed.

**Behavior changes:**
- Terminal logs no longer print raw user transcripts; caller phone and agent text are masked.
- `mask_pii()` now handles country-code phone numbers, known patient names, and common name-introduction phrases.
- Call history transcripts and summaries are stored with verified patient names masked.
- Abandoned locked slots are released on WebSocket cleanup when no booking was confirmed.
- Reschedule keeps the old appointment until the replacement booking succeeds, then cancels the old appointment.
- Scope detection now produces a bounded response for substantive off-topic unknowns and recovers on later in-scope turns.
- Optional Slack escalation notifications send masked summaries when `SLACK_WEBHOOK_URL` is configured.
- README, `.env.example`, and requirements were aligned with current runtime dependencies and Groq model.

**Tests:**
- `pytest tests/ -v` -> 66 passed, 2 deprecation warnings.

**Still requires live/manual work:**
- Make 5 live Twilio calls and verify dashboard data/masking.
- Record the split-screen demo video.
- Remove or archive legacy root demo scripts after the modular server is confirmed live.

---

### 2026-05-05 - Codex inspection + handoff logging

Codex inspected the repo without modifying application code, then added persistent handoff
logging under `dev/active/voice-agent/`. Root `AGENTS.md` remains unchanged and is still the
project instruction source.

**Files created:**
```
dev/active/voice-agent/codex-handoff.md - resume notes, risks, next tasks, run commands
```

**Files modified:**
```
dev/active/voice-agent/voice-agent-tasks.md   - this progress note
dev/active/voice-agent/voice-agent-context.md - pointer to the Codex handoff file
```

**Inspection result:**
- `pytest tests/ -v` -> 60 passed, 2 deprecation warnings.
- No package scripts/build config found beyond `requirements.txt`.
- Explicit unfinished work remains: optional Slack escalation, dashboard live-call validation,
  and demo video recording.

**Risks found at inspection time, later addressed in Codex finishing pass unless marked manual:**
1. PII is printed in terminal logs (`voice/twilio_handler.py`).
2. Name masking is not implemented in `guardrails/pii_masker.py`.
3. `.env.example` and README still reference the old Groq 3.1 model.
4. Locked slots are not released on call cleanup even though `release_slot()` exists.
5. Reschedule cancels the old appointment before replacement booking is confirmed.
6. Scope detector is implemented/tested but not wired into live routing.
7. `dashboard/app.py` imports pandas, but `requirements.txt` does not list it directly.

---

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
