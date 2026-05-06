# Codex Handoff - Voice Agent

**Last Updated:** 2026-05-06 README scanability update
**Purpose:** Fast resume notes for Codex sessions. Root `AGENTS.md` remains the project instruction file.

## Current Snapshot

- Project is complete, demo-ready, and portfolio-ready.
- Final live validation is complete for booking, reschedule, cancellation with confirmation, FAQ, escalation, Streamlit dashboard masking/status display, and barge-in behavior.
- Latest automated status: `pytest tests/ -v` -> 128 passed, 2 deprecation warnings.
- `README.md` has been rewritten as the final architecture, setup, demo, visual diagram, and technical-interest overview.
- The long ASCII architecture block has been trimmed to a compact text flow under the SVG diagram.
- Legacy Day 4 prototype scripts have been archived under `dev/archive/legacy-day4-pipeline/`.
- Current uncommitted work is docs-only: README visual/technical-interest/scanability improvements plus related active dev note updates.

## Maintained Runtime

- FastAPI + uvicorn server with Twilio Media Streams WebSocket.
- Deepgram Nova-2 streaming STT, mulaw 8 kHz.
- ElevenLabs `eleven_flash_v2_5` TTS with direct `ulaw_8000` output.
- LangGraph `StateGraph` orchestration.
- Groq via `langchain-groq`; runtime default is `llama-3.3-70b-versatile`.
- SQLite scheduling, patient lookup, and call history store.
- FAQ retrieval defaults to local markdown; ChromaDB remains available with `FAQ_RETRIEVAL_MODE=chroma`.
- Streamlit + pandas dashboard.
- pytest test suite.

## README Positioning

- Lead with the portfolio-ready status and visual architecture diagram.
- Explicitly call out that the project avoids hosted voice-agent platforms and implements the real-time media pipeline directly.
- Keep the recruiter-facing technical story focused on telephony, streaming audio, async orchestration, LangGraph state, slot locking, barge-in, PII masking, and dashboard visibility.
- Keep the text architecture below the SVG short so it supports accessibility/search without forcing visual scanners through duplicate ASCII.

## Demo-Validated Behaviors

- Booking verifies the caller, supports deterministic doctor selection, accepts inline date/time requests when the requested time is in the offered slots, locks the slot, collects reason, and confirms.
- Reschedule targets the latest appointment booked during the current call when available, books the replacement first, then cancels the old appointment.
- Cancellation targets the latest in-call appointment when available and requires explicit confirmation before cancelling.
- FAQ calls persist as `faq_answered` and dashboard labels them as `FAQ Answered`.
- Escalation generates a masked handoff summary and can optionally send a masked Slack notification.
- Caller phone, DOB contexts, and verified patient names are masked in logs/dashboard displays while appointment dates remain visible.
- Barge-in uses mulaw RMS VAD plus Twilio `mark`/`clear` handling.

## Run Commands

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python seed_database.py
python -m rag.ingestion

uvicorn voice.server:app --host 0.0.0.0 --port 8000 --reload
ngrok http 8000
streamlit run dashboard/app.py

pytest tests/ -v
```

Twilio webhook should point to `https://<PUBLIC_HOST>/incoming-call`, where `PUBLIC_HOST` is the ngrok hostname only, without protocol.

## Archived Prototype Scripts

The original Day 4 scripts are preserved for learning/reference only:

```text
dev/archive/legacy-day4-pipeline/full_pipeline.py
dev/archive/legacy-day4-pipeline/deepgram_feed.py
dev/archive/legacy-day4-pipeline/elevenlabs_stream.py
dev/archive/legacy-day4-pipeline/input_pipeline.py
```

The supported voice runtime is the modular `voice/` server.

## No Open Application Work

- Freeze app behavior unless a real bug is found.
- Do not run live Twilio/ngrok validation again by default; the final live scenarios are already validated.
- Leave `.env`, `clinic.db`, `rag/chroma_db`, and runtime service configuration untouched unless explicitly requested.
- Keep `pytest tests/ -v` green after any future changes.

## Logging Convention Going Forward

- Append session updates here when a session ends or pauses.
- Keep durable checklist changes in `voice-agent-tasks.md`.
- Keep architecture and decision notes in `voice-agent-context.md`.
- Do not store API keys, raw phone numbers, patient names, DOBs, or other PII in dev docs.
