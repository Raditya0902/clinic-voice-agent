# Voice Agent — Context

**Last Updated:** 2026-05-06 (final README/archive cleanup)

## Final Completion Status

- Project is complete, demo-ready, and portfolio-ready.
- Final live validation is complete for booking, reschedule, cancellation confirmation, FAQ, escalation, dashboard masking/status display, and barge-in.
- Latest automated status: `pytest tests/ -v` -> 128 passed, 2 deprecation warnings.
- The maintained runtime is the modular `voice/` server.
- Legacy Day 4 root scripts are archived under `dev/archive/legacy-day4-pipeline/` for learning/reference only.
- No further live Twilio validation is required for the final cleanup pass.

## Architecture Decisions

| Decision | Choice | Reason |
|---|---|---|
| Voice pipeline | Raw (no Vapi/Livekit) | Maximum control, resume value |
| STT | Deepgram Nova-2, streaming | Low latency, mulaw support |
| TTS | ElevenLabs Flash v2.5, streaming | Lower latency, natural voice, free tier |
| TTS Voice ID | ErXwobaYiN019PkySvjV (Antoni) | Works on free tier |
| LLM | Groq — LLaMA 3.3 70B | Free, fast inference |
| Agent framework | LangGraph | Stateful multi-agent routing |
| DB | SQLite | Simple, no external dependency |
| FAQ retrieval | Markdown by default; ChromaDB optional | Clean demo logs while preserving vector retrieval mode |
| Demo FAQ answers | 1-2 short phone-friendly sentences | Live phone audio needs concise answers over exhaustive policy detail |
| Demo workflow routing | Preserve verified booking/reschedule slot-filling turns | Prevent doctor/date/time answers from being misclassified as FAQ or a new workflow |
| Same-call appointment targeting | Latest appointment booked in the current call | Keeps long demo calls deterministic when a caller books, asks FAQ, then reschedules or cancels |
| Inline date/time reservation | Lock a clearly requested offered time during doctor/date collection | Avoids repeating all times when the caller says "tomorrow at 9 AM" and 9 AM is available |
| Doctor-name extraction | Deterministic match before LLM fallback | Clear demo doctor names should not repeat the doctor prompt |
| Server | FastAPI + uvicorn | Async WebSocket support |
| Tunnel | ngrok | Expose localhost to Twilio |
| Dashboard | Streamlit | Quick to build, auto-refresh |

## Prototype Lineage

The original Day 4 learning-plan voice pipeline included:
- FastAPI server with Twilio WebSocket handler
- Deepgram streaming STT (mulaw, 8kHz, endpointing 300ms)
- ElevenLabs TTS with Antoni voice — outputs `ulaw_8000` directly (no pydub/ffmpeg needed)
- Basic LLM response (hardcoded demo responses, replaced by LangGraph in Phase 3)

That prototype has been superseded by the modular `voice/` server. The old scripts are archived under `dev/archive/legacy-day4-pipeline/`.

## API Keys & Services (already set up)

- Twilio: Account active, phone number configured locally
- Deepgram: Account active, STT API key working
- ElevenLabs: Account active, TTS API key working
- Groq: Account active, LLaMA 3.3 70B key working
- ngrok: Account active, tunnel working

## Key Files to Reference

- `voice-agent-plan.md` — Full architecture, all agent specs, DB schema
- `voice-agent-tasks.md` — Implementation checklist

## Demo Polish Decisions (2026-05-06)

- FAQ-only calls should set `call_outcome="faq_answered"` once the FAQ agent
  provides an answer and no appointment or escalation outcome exists. This gives
  Streamlit a clear live-demo status instead of `Unknown`.
- When a verified caller is inside booking or reschedule and the last agent prompt
  asks which doctor they want, the next user turn should stay in the active
  appointment workflow even if `requested_doctor` is still empty. This is the
  earliest slot-filling state and should not depend on populated booking fields.
- FAQ answer generation should prioritize voice brevity. Markdown and Chroma
  retrieval remain unchanged, but the answer style should be 1-2 short sentences.
  If the clinic knowledge does not answer the question, use only the front-desk
  fallback sentence.
- Booking doctor selection should first use deterministic matching against the
  `get_all_doctors()` list. Accept full name, first+last, unique last name, and
  unique first name; if a name is ambiguous, fall back to the existing LLM extractor
  instead of guessing.
- If the booking doctor LLM returns a partial name, run that partial name through the
  same deterministic matcher before DB lookup. This catches returns like `Dr. Smith`
  when the real stored name is `Dr. Sarah Smith`.
- For live demo ergonomics, doctor and slot selection accept explicit option phrases
  such as `first`, `second`, `number two`, and `last`. Time selection also accepts
  `earliest`, `latest`, `noon`, and `midday`. Bare cardinal words are not option
  indexes unless paired with `number`, `option`, or `choice`.
- Same-call reschedule and cancellation target the latest appointment booked
  during that call by default. The state intentionally preserves
  `last_confirmed_appointment_*` across FAQ, farewell, and workflow transitions,
  then updates it after successful reschedule or clears it after confirmed
  cancellation. Separate calls remain fresh because `initial_call_state()` starts
  with no latest confirmed appointment.
- If a booking/reschedule response includes a clear offered time, such as
  "tomorrow at 9 AM" or "Dr. Chen tomorrow at 9 AM", booking locks that slot
  immediately and asks for the visit reason. If the time is unavailable or
  ambiguous, the agent still presents the available choices.

## Concurrency Note

The slot locking system (Section 7.6 of plan) is critical.
Two simultaneous callers booking the same slot must be handled via
optimistic locking with 60-second timeout. Never skip this.

---

## Phase 1 Refactoring Decisions (2026-05-03)

Everything below records what was actually built and where it differed
from the plan. Future Claude sessions: read this before touching voice/ or db/.

### 1. No audio conversion — pydub/ffmpeg dropped entirely

**Plan said:** "ElevenLabs outputs MP3. Use pydub + ffmpeg to convert to mulaw."
**Reality:** ElevenLabs SDK accepts `output_format="ulaw_8000"` and returns
Twilio-compatible bytes directly. No conversion step, no pydub, no ffmpeg.
`pydub` is NOT in requirements.txt. Do not add it.

### 2. WebSocket route name changed to match the plan

**Original Day 4 code:** `/twilio-stream`
**Plan spec / new code:** `/voice-stream`
The TwiML in `server.py` points to `wss://{host}/voice-stream`.
Twilio webhook URL stays `/incoming-call` (unchanged).

### 3. TwiML greeting is now clinic-branded

**Original:** "Connecting you to the demo agent."
**New:** "Welcome to Sunrise Health Clinic. How can I help you today?"
This matches the plan's demo script (Section 20).

### 4. Host detection uses PUBLIC_HOST env var, not NGROK_URL

**Plan said:** set `NGROK_URL` env var.
**New code:** `voice/server.py` reads `PUBLIC_HOST` (hostname only, no protocol).
Set it to your ngrok hostname, e.g. `abc123.ngrok-free.app`.
`NGROK_URL` is kept in `.env.example` as a legacy reference comment only.
This avoids stripping `https://` at runtime and is simpler.

### 5. ElevenLabs model is eleven_flash_v2_5, not turbo_v2

**Plan said:** "ElevenLabs Turbo v2, streaming"
**Used:** `eleven_flash_v2_5` — lower latency, same free-tier availability.
Voice ID stays `ErXwobaYiN019PkySvjV` (Antoni), confirmed working on free tier.

### 6. db/ module fully implemented in Phase 1, not Phase 4

The plan placed db/scheduling.py, db/patients.py, db/call_history.py in Phase 4.
All three were written in Phase 1 because the spec in the plan was complete enough
to implement immediately. Phase 4 tasks for these are pre-checked in tasks.md.

**db/scheduling.py** — adds `release_slot()` beyond the plan spec. Used to clean
up locks on call end if booking was never confirmed.

**db/call_history.py** — adds `get_recent_calls()` beyond the plan spec.
The dashboard (Phase 7) will need this; easier to have it now.

**db/patients.py** — adds `get_patient_by_id()` beyond the plan spec.
Needed by verification agent to re-fetch patient after initial lookup.

### 7. CallSession owns both queues

**Original Day 4 code:** `audio_queue` and `finals_queue` were local variables
in the WebSocket handler function, passed into `run_deepgram_finals()`.
**New code:** both queues are attributes on `CallSession`. This keeps all
per-call state in one place for when LangGraph state is added in Phase 3.

### 8. Barge-in is opt-in via BARGE_IN env var (default off)

`BARGE_IN=0` by default. Set `BARGE_IN=1` to cancel TTS when patient speaks.
The original code warned about this (continuous audio would mute the agent);
the env var makes it explicit and safe.

### 9. ApiError handling lives in session.py, not twilio_handler.py

ElevenLabs 402 errors (voice not on free tier) are caught inside
`CallSession.speak()`. The handler stays clean and doesn't need to know
about TTS internals. If 402 fires, it prints guidance and the turn is skipped.

### 10. Original Day 4 files archived

`full_pipeline.py`, `deepgram_feed.py`, `elevenlabs_stream.py`, `input_pipeline.py`
are preserved under `dev/archive/legacy-day4-pipeline/`. They are superseded by the
modular `voice/` server and are kept only for learning/reference.

### 11. Python 3.13 compatibility — datetime.utcnow() replaced

`datetime.utcnow()` is deprecated in Python 3.12+ and will be removed.
All db/ modules use `datetime.now(timezone.utc)` instead.
The `timezone` import is `from datetime import datetime, timedelta, timezone`.

---

## Phase 2 RAG Decisions (2026-05-03)

### 1. query() and format_context() take explicit persist_dir/collection_name

Plan showed module-level globals only. Instead, `rag/vectorstore.py::query()` accepts
`persist_dir` and `collection_name` as parameters (defaulting to env vars).
This makes tests trivially safe — they pass a `tmp_path` ChromaDB and never touch the
real `./rag/chroma_db` on disk. Do not remove these parameters.

### 2. format_context() helper added (not in plan)

`format_context(chunks: list[dict]) -> str` joins retrieved chunk texts with double
newlines into a single LLM-ready string. Both `faq_agent.py` and future agents use
this so the joining logic lives in one place.

### 3. hours_and_location.md has redundant sentences for recall

The file ends with plain-prose restatements of the hours
("The clinic opens at 8:00 AM on weekdays..."). This improves semantic retrieval when
callers ask in casual phrasing ("are you open Saturday?"). Keep them.

### 4. Run ingestion before starting the server

`python -m rag.ingestion` must be run once to populate `./rag/chroma_db`.
It upserts, so re-running is safe. It is NOT run automatically by the server on startup.

---

## Phase 3 LangGraph Decisions (2026-05-03)

### 1. CallState and CallIntent live in graph/state.py, not graph/workflow.py

The plan put everything in `workflow.py`. This causes circular imports:
`workflow.py` imports agents → agents import `CallState` → `CallState` is in `workflow.py`.
Fix: `graph/state.py` owns the types. All agents and router import from there.
`workflow.py` only imports from agents and router.

### 2. get_compiled_graph() is lazy — graph not built at import time

`workflow.py` exports `get_compiled_graph()` instead of a module-level `compiled_graph`.
The graph builds on the first call. This means:
- Tests that don't need the graph don't pay the build cost.
- Imports don't fail if agents have any startup errors.
`voice/session.py` calls `get_compiled_graph().invoke(state)` inside `process_turn()`.

### 3. LangGraph state lists updated with concatenation, not append

LangGraph copies state between nodes. Mutating a list in place (`.append()`)
can cause subtle bugs where two nodes see different list lengths.
`intent_agent.py` does: `state["previous_intents"] = state["previous_intents"] + [new_intent]`
`session.py` does the same for `conversation_history`.
Always use concatenation, not `.append()`, when updating list fields on CallState.

### 4. max_tokens=200 enforced on ChatGroq

Voice responses must be short (plan says ≤3 sentences). `get_llm()` sets `max_tokens=200`
so the LLM cannot generate a long answer even if the prompt doesn't instruct it to be brief.
This is a hard cap, not just a prompt instruction.

### 5. escalation_agent is fully functional from Phase 3 onward

The stub agents (booking, reschedule, cancellation, verification) return placeholder
messages pointing to the phone number. But `escalation_agent.py` is real: it sets
`escalated=True`, `call_outcome="escalated"`, and a full handoff message.
Slack webhook and call summary generation are added in Phase 6.

### 6. Caller phone number captured from Twilio "start" event

`voice/twilio_handler.py` reads `data["start"]["from"]` for the caller's phone number
and stores it in `session.caller_phone`. `session.init_state()` is called immediately
after, so `CallState.caller_phone` is populated from the first turn.
The field name in the Twilio payload is `"from"` (lowercase), not `"From"`.

### 7. test_voice_modules_import now passes (was skipped in Phase 1)

In Phase 1 it was skipped because deepgram/elevenlabs weren't installed.
The Phase 3 imports (langchain_groq, langgraph) are in the same env that
runs pytest, so all voice module imports now resolve. The test passes, not skips.

---

## Phase 8 Polish + Live Testing Decisions (2026-05-03) — continued

### 9. ElevenLabs speed parameter not supported in this SDK version

`speed=0.85` passed to `client.text_to_speech.stream()` raises `TypeError: unexpected keyword argument 'speed'`.
The ElevenLabs Python SDK (elevenlabs>=1.5.0) does not expose `speed` as a top-level parameter on `stream()`.
Removed. Used `stability=0.6` instead (was 0.5) — slightly more deliberate pacing, no SDK dependency.
Do not re-add `speed=` to `_synthesize_ulaw` without verifying the SDK version supports it.

### 10. Verification agent now reads conversation history for multi-turn name+DOB

Original: `_extract_name_dob(utterance)` only looked at the current turn. If the patient said their
name in turn N and DOB in turn N+1, neither turn had both fields and verification looped forever.
Fix: `_extract_name_dob(utterance, history)` concatenates the last 6 patient turns into one context
block for the LLM. The LLM can now piece together name+DOB even when given across separate messages.
Also improved partial-extraction prompts: if only name found → "And your date of birth?";
if only DOB found → "And your full name?" instead of repeating the full question.

### 11. TTS exceptions now caught broadly — session limit surfaced in logs

`speak()` previously only caught `ApiError`. Any other ElevenLabs error (session limit,
concurrent stream limit, network error) propagated up and crashed the WebSocket handler.
Added `except Exception as exc: print(f"[tts] error — {type(exc).__name__}: {exc}")` after
the `ApiError` handler. TTS failures now log to Terminal 1 and the call continues (silently,
no audio for that turn) rather than crashing. The `[tts]` prefix makes these easy to grep.

ElevenLabs free tier limit: ~2 concurrent streams. Stale sessions from errored calls may hold
the limit open for 30–60 seconds. If hearing no audio, wait and retry.

---

## Phase 8 Polish + Live Testing Decisions (2026-05-03)

### 1. Groq model llama-3.1-70b-versatile was decommissioned — updated to 3.3

`llama-3.1-70b-versatile` was removed by Groq between Phase 3 (build time) and Phase 8 (live testing).
Updated in both `.env` (`LLM_MODEL=llama-3.3-70b-versatile`) and as the default fallback in
`graph/llm.py`. The LLM singleton must be invalidated on model change — uvicorn `--reload`
handles this by restarting the process. Do not revert to 3.1.

### 2. UNKNOWN intent clarifies instead of escalating

Originally, confidence < 0.5 → `ESCALATE`. This caused silent Groq failures (decommissioned model)
to auto-escalate every call. Changed to `UNKNOWN` which routes to END with a clarify response set
in `intent_agent`. `route_by_intent` now returns `"unknown"` → mapped to `END` in the workflow.
The LLM error is now printed (`[intent] ERROR — Groq call failed: ...`) so failures are visible.

### 3. FAREWELL intent added — keyword-based, no LLM

When patient says "bye", "goodbye", "that's all", "no that's it", etc., the intent_agent detects
it before the Groq call (keyword match) and sets `CallIntent.FAREWELL`. Routes to `farewell_agent`
which returns a goodbye message and marks `call_outcome = "completed"` if not already set.
This prevents farewell phrases from being misclassified as booking or triggering escalation.

### 4. Barge-in enabled by default for demo (BARGE_IN=1 in .env)

Set to 1 in `.env` for live testing. This cancels TTS playback when Deepgram detects patient speech.
Context.md Phase 1 noted barge-in is opt-in — it was off for safety during development.
For demo recording, leave BARGE_IN=1 so the agent feels responsive and natural.

### 5. TTS speed set to 0.85 via ElevenLabs speed parameter

`speed=0.85` passed to `client.text_to_speech.stream()` in `elevenlabs_tts.py`.
Supported in ElevenLabs Flash v2.5. Makes speech 15% slower — more natural for phone calls
and easier for Deepgram to re-transcribe (avoids clipping at sentence end). Value range 0.7–1.2.

### 6. Seed clears slots before re-inserting — safe to run multiple times

Slots table had no unique constraint. Running `seed_database.py` twice created duplicate slots
(agent read "8:00 AM, 8:00 AM, 9:00 AM, 9:00 AM"). Fixed by `DELETE FROM slots` before the
insert loop. Doctors and patients use `INSERT OR IGNORE` and are unaffected. Re-seeding is now
always safe and idempotent.

### 7. PUBLIC_HOST vs NGROK_URL — server reads PUBLIC_HOST only

The original `.env` only had `NGROK_URL`. `voice/server.py` reads `PUBLIC_HOST` (see Phase 1
Decision 4). If `PUBLIC_HOST` is missing, the server falls back to the request `host` header,
which works for the incoming-call webhook but produces the wrong WebSocket URL in TwiML.
Always set `PUBLIC_HOST` to the ngrok hostname (no `https://`, no trailing slash).

### 8. Stale processes on port 8000 cause 404s — kill before restarting

`uvicorn voice.server:app --host 0.0.0.0 --port 8000 --reload` starts new worker processes.
If old Python processes remain on port 8000 (e.g. from a previous session), curl hits the
old process which has no routes → 404. Diagnose with `lsof -i :8000`, kill stale PIDs.

---

## Phase 7 Dashboard Decisions (2026-05-03)

### 1. sys.path.insert at top of dashboard/app.py — no package install needed

Running `streamlit run dashboard/app.py` sets CWD to project root but doesn't add it to
`sys.path` automatically. `dashboard/app.py` inserts the parent directory at `sys.path[0]`
so `from db.call_history import ...` and `from guardrails.pii_masker import ...` resolve
without needing a `setup.py` or `pyproject.toml`. Do not remove this line.

### 2. Auto-refresh via time.sleep(2) + st.rerun() — no extra dependency

`streamlit-autorefresh` is a third-party component. The native approach (`time.sleep(2)` at
the bottom of the script followed by `st.rerun()`) achieves the same result with zero extra
deps. Every 2 seconds the entire script re-executes, re-queries the DB, and re-renders.
This is fine for a demo; for production use `st_autorefresh` or a websocket push approach.

### 3. get_recent_calls() extended to return all dashboard fields

The original (Phase 1) version returned 7 fields. Phase 7 extended it to return 11 fields:
added `duration_seconds`, `transcript` (parsed from JSON), `intent_sequence` (parsed from
JSON), and `sentiment_avg`. The transcript and intent_sequence are decoded from their stored
JSON strings into Python objects so the dashboard doesn't need to call `json.loads()`.

### 4. get_dashboard_stats() added for the top metric tiles

Computes 4 values in a single DB connection: active call count (no end_time), today's call
count (start_time LIKE today%), success rate (booked+cancelled / completed), and avg duration
(AVG of duration_seconds). Kept in `db/call_history.py` consistent with the "no raw SQLite
in UI code" rule.

### 5. Transcript rendered with inline HTML via st.markdown(unsafe_allow_html=True)

Streamlit has no native chat-bubble component. Patient turns use a light-blue background
div; agent turns use light-green. `mask_pii()` is applied to each turn's text before
rendering. This is the only place in the codebase that uses `unsafe_allow_html=True` — keep
it isolated to the transcript renderer function `_render_transcript()`.

### 6. Outcome pie chart replaced with bar chart — no Altair/Plotly dependency

The plan said "pie chart" for outcomes. Streamlit's built-in `st.bar_chart()` requires no
extra dependencies and renders cleanly. A pie chart would need `plotly` or `altair`.
Since requirements.txt already includes `streamlit`, using only built-in chart primitives
keeps the dependency count low.

---

## Phase 6 Safety Layer Decisions (2026-05-03)

### 1. Sentiment scoring is keyword-based, not LLM-based

Running a Groq call on every turn just for frustration scoring adds ~300ms latency and token cost.
Keyword matching is instant and good enough for demo: `_FRUSTRATION_WORDS` set scores 0.15 per hit;
explicit escalation phrases ("speak to a manager") add 0.4. Score accumulates across turns.
Auto-escalates at threshold 0.75. LLM approach would be Phase 8 polish item.

### 2. intent_agent skips LLM call when guardrail_triggered is set

`sentiment_agent` runs first. If it sets `guardrail_triggered` ("abuse" or "frustration"),
it also sets `current_intent = ESCALATE`. `intent_agent` checks `state.get("guardrail_triggered")`
at the top and returns early — no LLM call, no override of the escalation intent.
This saves a Groq call and keeps the escalation path latency-free.

### 3. Abuse terms are genuinely abusive only — frustration words stay separate

"terrible", "useless", "worst" were initially in _ABUSE_TERMS but moved out.
Abuse detector should only flag personal attacks and profanity. Frustration words cover
general negative sentiment. Mixing them caused a test failure: "terrible" triggered the
abuse path and skipped the frustration score update.

### 4. call_summary generated in escalation_agent, masked with PII masker

`_build_summary()` builds a plain-text summary from state fields: patient name, intents,
doctor, date, appointment ID, guardrail reason, turn count. Then `mask_pii()` strips any
phone/DOB/email patterns before storing. The summary is stored in `state["call_summary"]`
and written to `call_history.call_summary` via `end_call_record()`.

### 5. Call history stored in twilio_handler finally block, not in agents

`start_call_record()` is called in the "start" event handler (immediately after session init).
`end_call_record()` is called in the `finally` block regardless of how the session ends
(normal stop, error, or dropped call). Both calls are wrapped in try/except so a DB failure
never crashes the voice session. The transcript is PII-masked before storage.

### 6. Fallback policies already handled by existing flow — no new nodes needed

- Poor audio / short utterance: booking/verification agents ask again when they can't extract info
- Max verification retries: `route_after_verification` escalates at `verification_attempts >= 2`
- Slot taken: `booking_agent._handle_slot_selection` removes taken slot, presents remaining
- No slots: `_fetch_and_present_slots` clears `requested_date`, asks patient to pick another
No additional fallback nodes were added to the LangGraph workflow.

---

## Phase 5 Reschedule + Cancel Decisions (2026-05-03)

### 1. reschedule_agent delegates to booking_agent after cancelling old slot

**Why:** The slot-filling logic (doctor → date → slots → lock → reason → confirm) is identical
for both new bookings and rescheduled ones. Rather than duplicating it, `reschedule_agent`
handles only stage 1 (find + cancel old appointment), then imports and calls `booking_agent(state)`
for all subsequent turns. The import is inside the function body (not at module level) to
avoid circular imports at graph build time.

### 2. reschedule_agent pre-populates requested_doctor from the old appointment

When the old appointment is cancelled, `requested_doctor` and `requested_doctor_id` are set
to the old doctor's values. This skips the doctor-selection turn in the booking flow — the
patient goes straight to being asked for a new date. If the patient wants a different doctor,
they'd need to call back; accepted simplification for Phase 5.

### 3. Both agents cancel the earliest upcoming appointment when multiple exist

Production would present a list and ask which appointment to cancel/reschedule.
Phase 5 simplifies: always take `appointments[0]` (earliest by date + start_time).
Noted here so Phase 8 polish can address if needed.

### 4. cancellation_agent now requires confirmation

The original Phase 5 simplification was single-turn cancellation. Live validation showed
that was too destructive, so cancellation now identifies the target appointment and asks
for confirmation before calling `cancel_appointment()`. Same-call cancellation targets the
latest appointment booked during the current call before falling back to the earliest
upcoming DB appointment.

### 5. db/appointments.py added for appointment lookups

`get_patient_appointments(patient_id)` joins appointments with doctors, filters for
`status='confirmed'` and `date >= today`, ordered ascending. Returns list of dicts with
`id, doctor_id, doctor_name, date, start_time, reason`.
Agents never query the appointments table directly — always go through this function.

---

## Phase 4 Booking Decisions (2026-05-03)

### 1. verification_agent leaves agent_response="" on success

**Why:** When verification succeeds, LangGraph routes immediately to `booking_agent` in
the same turn. If `verification_agent` sets a response ("Identity verified!"), `booking_agent`
overwrites it. Instead, `verification_agent` sets `agent_response=""` on success and lets
`booking_agent` produce the full response — greeting the patient by first name and asking
which doctor they'd like. This gives one clean, combined message per turn.

On failure or missing info, `verification_agent` sets its own response as usual (the routing
returns END before booking_agent runs).

### 2. Booking agent is a linear state machine — no explicit step field

**Why avoided:** Adding a `booking_step: str` field to CallState was considered but rejected.
The current stage is fully inferable from which state fields are populated:
- No `requested_doctor` → doctor stage
- No `requested_date` → date stage
- `requested_date` set but `available_slots` empty and `locked_slot_id` None → fetch slots
- `available_slots` set, `locked_slot_id` None → slot selection stage
- `locked_slot_id` set, `reason_for_visit` None → reason stage
- All set → confirm

This avoids adding state that can get out of sync with the actual fields.

### 3. _handle_reason_stage reads conversation_history to detect context

**Pattern:** When `locked_slot_id` is set and `reason_for_visit` is None, the agent is
either (a) just locked the slot and needs to ask for reason, or (b) the patient just gave
the reason. These look identical in state. Resolution: inspect the last agent message in
`conversation_history`. If it contains `"reason for your visit"`, the patient is responding
to that question → extract utterance as reason. Otherwise → ask.

This works because `session.py` appends the agent response to history AFTER the LangGraph
invoke, so during the next turn's invoke the history correctly shows the previous agent turn.

### 4. Date fetch happens in the same turn as date extraction

`_handle_date_stage` calls `_fetch_and_present_slots` directly when a date is successfully
extracted. This means the patient says "this Friday" and in the same response hears the
available slots — one less round-trip compared to asking "OK, fetching..." and then presenting
slots next turn. `booking_agent` still has the `if not available_slots` guard for safety but
it should not fire in normal flow.

### 5. requested_doctor_id stored in state to avoid repeated DB lookups

`booking_agent` sets `requested_doctor_id` in state when the doctor is first resolved.
Subsequent turns use this ID directly for `get_available_slots()` rather than re-querying
`find_doctor_by_name()` every time. This also makes the doctor resolution deterministic —
even if `find_doctor_by_name()` would return a different result later (e.g., if DB changed),
the booking stays consistent.

### 6. Slot lock failure removes taken slot and re-presents remaining options

When `lock_slot()` returns False (optimistic lock lost to a concurrent call), the taken slot
is removed from `available_slots` in state and the agent presents the remaining options.
If all slots are gone, `requested_date` is cleared so the patient can pick a new date.
This implements the plan's Section 7.6 concurrency requirement without any extra DB queries.

### 7. db/doctors.py added beyond plan spec

The plan had no dedicated doctors module. `db/doctors.py` adds `get_all_doctors()` and
`find_doctor_by_name(name_fragment)` (LIKE search). These are used by `booking_agent` to
build the doctor list prompt for LLM extraction and to resolve names to IDs.
Do not query the doctors table directly from agents — always go through `db/doctors.py`.

### 8. pytest requires explicit install in .venv — no pytest in venv by default

The .venv was created without pytest. Must run `.venv/bin/pip install pytest` before
running the test suite. The CLAUDE.md command `pytest tests/ -v` should be run as
`.venv/bin/python -m pytest tests/ -v` or with pytest installed in the venv.

---

## Codex Handoff Logging (2026-05-05)

Codex added `dev/active/voice-agent/codex-handoff.md` as the resume file for future
sessions. Keep root `AGENTS.md` unchanged; it is the project instruction file, not a
session log.

Use the files this way:
- `voice-agent-tasks.md` - durable checklist and progress notes.
- `voice-agent-context.md` - architecture decisions and implementation rationale.
- `codex-handoff.md` - latest resume snapshot, inspection findings, and next actions.

Do not write secrets or raw PII into any dev docs.

---

## Codex Finishing Decisions (2026-05-05)

### 1. Logs favor privacy over full transcript debugging

`voice/deepgram_stt.py` and `voice/twilio_handler.py` no longer print raw patient
transcripts. The handler logs only that a transcript was received; agent responses and
caller phone values are passed through `mask_pii()`.

### 2. Name masking is best-effort plus known-patient masking

`mask_pii()` now accepts optional known names. Once verification succeeds, call-history
transcripts and summaries are masked with the verified patient name and its name parts.
It also masks common phrases like "my name is ..." before storage/display. This avoids
adding patient-name fields to every call-history row.

### 3. Reschedule is no longer destructive up front

`reschedule_agent` now stores the existing appointment and pre-fills the doctor, but it
does not cancel the old appointment until the replacement booking has succeeded. If the
new booking succeeds but old cancellation fails, the call is escalated so the front desk
can resolve the double-booking risk.

### 4. Scope guardrail is intentionally narrow

`scope_detector` is wired through low-confidence unknown intent handling. It only fires
for substantive off-topic utterances, not filler like "uh, I don't know"; this prevents
normal hesitation during voice calls from trapping the user in an out-of-scope state.
An out-of-scope state is cleared on the next turn so the caller can recover.

### 5. Slack escalation is optional and masked

`escalation_agent` sends a Slack webhook only when `SLACK_WEBHOOK_URL` is set. The payload
uses the same masked call summary and does not log the webhook URL. Slack failures are
logged by exception type only and do not break the call flow.

### 6. Validation status

Superseded final status: `pytest tests/ -v` passes with 128 tests and 2 dependency
deprecation warnings. Final live Twilio/dashboard validation is complete.

### 7. Barge-in must not use raw Twilio media packets

Live testing showed no audible agent voice and no `[latency] tts_first_frame=...` logs.
The likely cause was `BARGE_IN=1` cancelling speech on every inbound Twilio media packet;
Twilio sends continuous media, including silence/noise, while the agent is preparing TTS.

`voice/twilio_handler.py` now treats raw media only as Deepgram input. With barge-in enabled,
TTS runs in the background and can be cancelled when a finalized new utterance is processed,
not on every raw audio packet. This preserves interruption behavior without muting the agent.

### 8. Dashboard transcript cards need explicit text color

Streamlit dark mode made transcript text white on pale custom HTML cards. The dashboard now
sets `color:#111827` on patient/agent transcript cards so masked transcripts remain readable.

### 9. Native dependency panics must not kill calls

Live FAQ testing triggered a ChromaDB Rust/PyO3 panic while creating a persistent client.
This propagated as a non-standard `BaseException`, so normal `except Exception` handlers did
not catch it and the WebSocket crashed.

`faq_agent` now catches non-system `BaseException` around RAG retrieval and falls back to
direct markdown context from `rag/clinic_knowledge`. `CallSession.process_turn()` also catches
non-system `BaseException` around LangGraph invocation so a native library panic returns a
technical fallback instead of terminating the call. It still re-raises cancellation and
process-control exceptions.

### 10. Barge-in uses mulaw VAD

Raw Twilio media is continuous, so presence of media is not enough to infer interruption.
`voice/barge_in.py` decodes inbound G.711 mulaw frames and uses RMS energy over sustained
frames to detect caller speech. Defaults are conservative:
- `BARGE_IN_RMS_THRESHOLD=900`
- `BARGE_IN_SPEECH_FRAMES=4`
- `BARGE_IN_SILENCE_FRAMES=2`

If live interruption feels insensitive, lower the threshold to `700`. If silence/noise
cancels speech, raise it to `1100` or increase `BARGE_IN_SPEECH_FRAMES`.

### 11. Barge-in must clear Twilio's playback buffer

ElevenLabs audio can be generated and sent to Twilio faster than the caller hears it.
That means the local `speak_task` may finish while Twilio is still playing buffered TTS.
Cancelling the local task alone does not stop audio already queued at Twilio.

Outbound TTS now sends a Twilio `mark` after media frames and keeps `session.speaking`
true until Twilio returns that mark. On barge-in or a finalized new user turn,
`session.cancel_speak(..., clear_buffer=True)` sends Twilio `clear` so buffered audio is
flushed immediately.

### 12. Cancellation is confirm-before-destructive

Live cancellation testing exposed that `cancellation_agent` cancelled the earliest
appointment immediately after verification. If the caller later said another
cancel-like utterance, the next appointment could be cancelled in the same call.

Cancellation now has two stages: identify the earliest upcoming appointment and ask for
confirmation, then cancel only after an affirmative response. Short yes/no responses to
that confirmation are routed deterministically in `intent_agent` so the LLM classifier
does not lose the pending workflow. `reschedule_agent` also ignores appointment state
left over from a completed cancellation.

### 13. Unknown turns must not reuse stale agent_response

LangGraph leaves state fields in place between turns. If `intent_agent` classified a turn
as `unknown` with confidence exactly `0.5`, the old code did not set a new response because
it only handled confidence below `0.5`. The router then ended the graph with the prior
agent response still in state.

`intent_agent` now sets the unknown fallback for any `CallIntent.UNKNOWN`, regardless of
confidence. It also routes a negative answer after an "anything else?" prompt directly to
farewell without an LLM call.

### 14. Appointment dates are not DOBs

The PII masker previously masked every ISO date as `[DOB]`, so agent logs/dashboard text
showed appointment dates as `[DOB]`. This was privacy-safe but degraded operational
readability. `mask_pii()` now masks dates only when they appear in DOB/birthday contexts
such as "born on", "date of birth", or "DOB". Appointment dates in booking/cancellation
confirmations remain visible in masked logs and dashboard displays.

### 15. Caller phone is passed as a Twilio stream parameter

Live calls showed `from=unknown` because the Twilio Media Stream `start` payload did not
include the webhook's `From` field directly. `/incoming-call` now parses the Twilio POST
body and injects the caller phone as a `<Parameter name="caller_phone" ...>` inside the
`<Stream>`. `twilio_handler` reads `start.customParameters.caller_phone` before falling
back to `start.from` or `unknown`.

### 16. Active workflows override noisy intent classification

Live testing showed the LLM classifier can misclassify short slot-filling utterances.
In one reschedule flow, a time selection was classified as `booking`, so the new slot was
booked without returning to `reschedule_agent` to cancel the old appointment. In a booking
flow, a time-selection turn briefly classified as `reschedule`.

`intent_agent` now checks the last agent prompt before calling the LLM. If the prompt is a
transactional slot-filling prompt and booking/reschedule state is already in progress, it
routes directly to the active workflow. Farewell, "anything else?" negation, and pending
cancellation confirmation still take precedence.

### 17. Latest live validation status

After the active workflow routing fix, reschedule live validation succeeded. The final
reschedule response explicitly stated that the previous appointment was cancelled and the
new appointment was confirmed, which verifies that `reschedule_agent` regained control
after booking the replacement slot.

Operational status:
- Booking works end to end.
- Reschedule works end to end after the in-progress routing fix.
- Cancellation confirmation works and prevents accidental destructive cancellation.
- Escalation handoff response works.
- Barge-in works with Twilio `clear` and buffered playback tracking.
- Caller phone and appointment-date masking/logging are now correct.

Final validation additions:
- Streamlit dashboard masking and FAQ outcome display were validated.
- Same-call latest-appointment targeting was validated for reschedule/cancel.
- Inline date/time reservation was validated for booking/reschedule.

### 18. FAQ demo mode and offered-slot parsing

FAQ retrieval now has an explicit mode switch:
- `FAQ_RETRIEVAL_MODE=markdown` (default): skip Chroma entirely and retrieve context from
  the clinic markdown files. Use this for clean demos.
- `FAQ_RETRIEVAL_MODE=chroma`: use the existing ChromaDB vector retrieval path. Chroma
  exceptions still fall back to markdown context.

Booking slot selection now runs deterministic parsing before the LLM slot extractor.
It maps common spoken forms for offered slots, including `10`, `10 AM`, `ten`,
`ten AM`, `ten o'clock`, and `the 10 o'clock one`. If the parsed time is not in the
offered list or is ambiguous, booking falls back to the existing LLM extractor.

Final validation additions:
- Markdown FAQ mode is the default demo path.
- ChromaDB remains optional and no longer blocks live FAQ calls.
