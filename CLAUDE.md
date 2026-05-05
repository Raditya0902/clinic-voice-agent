# Clinic Voice Agent — Claude Code Instructions

## Project
Healthcare clinic voice agent with raw Twilio + Deepgram + ElevenLabs pipeline and LangGraph multi-agent orchestration.

## Commands
```bash
# Run voice server
uvicorn voice.server:app --host 0.0.0.0 --port 8000 --reload

# Run Streamlit dashboard
streamlit run dashboard/app.py

# Start ngrok tunnel
ngrok http 8000

# Seed the database
python seed_database.py

# Ingest RAG knowledge base
python -m rag.ingestion

# Run tests
pytest tests/ -v
```

## Project Structure
- `voice/` — Twilio WebSocket, Deepgram STT, ElevenLabs TTS, audio utils
- `agents/` — LangGraph agent implementations (intent, booking, FAQ, etc.)
- `graph/` — LangGraph workflow and routing
- `db/` — SQLite models, scheduling logic, patient lookup
- `rag/` — ChromaDB setup, clinic knowledge ingestion
- `guardrails/` — PII masking, abuse detection, scope detection
- `dashboard/` — Streamlit ops monitoring
- `tests/` — pytest test files

## Key Conventions
- All async code uses `asyncio` patterns (no threading)
- Audio format: Twilio sends/receives mulaw 8kHz. ElevenLabs outputs MP3. Always convert.
- LLM calls go through Groq (LLaMA 3.1 70B). Keep responses concise — this is voice, not text.
- Agent responses must be under 3 sentences. Long responses sound terrible over the phone.
- PII (names, DOB, phone) must be masked in all logs and dashboard displays.
- Slot locking uses optimistic locking with 60-second timeout.
- All DB operations in `db/` module — agents never query SQLite directly.

## Task Workflow
- Always check `dev/active/` for existing task files before starting work
- For any task taking more than 30 minutes, create dev docs (see dev/active/)
- Plan before implementing. No jumping straight into code.
- After making code changes, run `pytest` and fix errors before considering done.

## Environment
- Python 3.11+
- API keys in `.env` (never hardcode)
- SQLite at `./clinic.db`
- ChromaDB at `./rag/chroma_db`
