"""Smoke tests for the refactored voice pipeline modules."""
import asyncio
import importlib
import json
from unittest.mock import MagicMock, patch

import pytest


def test_voice_modules_import():
    """All voice/ submodules must be importable (skipped if third-party deps not installed)."""
    # Check required third-party packages first; skip the test if any are missing.
    required = ["fastapi", "deepgram", "elevenlabs", "dotenv"]
    missing = []
    for pkg in required:
        try:
            importlib.import_module(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        pytest.skip(f"Third-party packages not installed: {', '.join(missing)}")

    modules = [
        "voice.audio_utils",
        "voice.barge_in",
        "voice.deepgram_stt",
        "voice.elevenlabs_tts",
        "voice.session",
        "voice.twilio_handler",
        "voice.server",
    ]
    for mod in modules:
        assert importlib.import_module(mod), f"Failed to import {mod}"


def test_db_modules_import():
    modules = [
        "db.models",
        "db.scheduling",
        "db.patients",
        "db.call_history",
    ]
    for mod in modules:
        assert importlib.import_module(mod), f"Failed to import {mod}"


def test_seed_and_schema(tmp_path):
    """create_tables + seed should produce the expected row counts."""
    from db.models import create_tables
    from db.scheduling import get_available_slots
    from db.patients import lookup_patient
    import sqlite3
    import sys
    import os

    db = str(tmp_path / "test.db")
    create_tables(db)

    # Import seed function with overridden DB_PATH
    import seed_database
    seed_database.seed(db)

    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM doctors").fetchone()[0] == 4
    assert conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0] == 4
    assert conn.execute("SELECT COUNT(*) FROM slots").fetchone()[0] > 0
    conn.close()

    # Patient lookup
    patient = lookup_patient("John Doe", "1990-03-05", db)
    assert patient is not None
    assert patient["first_name"] == "John"

    # Unknown patient returns None
    assert lookup_patient("Nobody Here", "2000-01-01", db) is None


def test_slot_locking(tmp_path):
    """lock_slot / confirm_booking / cancel_appointment round-trip."""
    from db.models import create_tables
    from db.scheduling import lock_slot, confirm_booking, cancel_appointment, get_available_slots
    import sqlite3

    db = str(tmp_path / "test.db")
    create_tables(db)

    import seed_database
    seed_database.seed(db)

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT id, date FROM slots WHERE is_available = 1 LIMIT 1"
    ).fetchone()
    conn.close()
    assert row, "No slots were seeded"

    slot_id, date = row

    # Lock it
    assert lock_slot(slot_id, "CALL001", db)
    # Same call can re-lock
    assert lock_slot(slot_id, "CALL001", db)
    # Different call cannot lock
    assert not lock_slot(slot_id, "CALL002", db)

    # Confirm booking
    appt_id = confirm_booking(slot_id, "CALL001", patient_id=1, reason="Checkup", db_path=db)
    assert appt_id > 0

    # Slot should now be unavailable
    conn = sqlite3.connect(db)
    avail = conn.execute("SELECT is_available FROM slots WHERE id = ?", (slot_id,)).fetchone()[0]
    conn.close()
    assert avail == 0

    # Cancel appointment frees the slot
    cancel_appointment(appt_id, db)
    conn = sqlite3.connect(db)
    avail = conn.execute("SELECT is_available FROM slots WHERE id = ?", (slot_id,)).fetchone()[0]
    conn.close()
    assert avail == 1


def test_release_slot_allows_another_call_to_lock(tmp_path):
    from db.models import create_tables
    from db.scheduling import lock_slot, release_slot
    import sqlite3

    db = str(tmp_path / "test.db")
    create_tables(db)

    import seed_database
    seed_database.seed(db)

    conn = sqlite3.connect(db)
    slot_id = conn.execute("SELECT id FROM slots WHERE is_available = 1 LIMIT 1").fetchone()[0]
    conn.close()

    assert lock_slot(slot_id, "CALL001", db)
    assert not lock_slot(slot_id, "CALL002", db)

    release_slot(slot_id, "CALL001", db)

    assert lock_slot(slot_id, "CALL002", db)


def test_barge_in_detector_ignores_silence_and_detects_speech():
    from voice.barge_in import BargeInDetector, mulaw_rms

    silence = b"\xff" * 160
    loud = b"\x00" * 160

    assert mulaw_rms(silence) == 0.0
    assert mulaw_rms(loud) > 900

    detector = BargeInDetector(threshold=900, speech_frames=3, silence_frames=2)
    assert detector.is_speech(silence) is False
    assert detector.is_speech(loud) is False
    assert detector.is_speech(loud) is False
    assert detector.is_speech(loud) is True

    detector.reset()
    assert detector.is_speech(loud) is False


def test_speak_keeps_playback_active_until_twilio_mark():
    from voice.session import CallSession

    class DummyWebSocket:
        def __init__(self):
            self.messages = []

        async def send_text(self, message):
            self.messages.append(json.loads(message))

    async def fake_tts_frames(_text):
        yield b"\xff" * 160

    session = CallSession()
    session.stream_sid = "STREAM001"
    websocket = DummyWebSocket()

    with patch("voice.session.text_to_speech_mulaw_frames", fake_tts_frames):
        asyncio.run(session.speak("Hello", websocket))

    assert session.speaking is True
    assert session.playback_mark_name == "tts-1"
    assert [m["event"] for m in websocket.messages] == ["media", "mark"]

    session.handle_playback_mark("tts-1")

    assert session.speaking is False
    assert session.playback_mark_name is None


def test_cancel_speak_clears_twilio_buffer_after_local_task_finished():
    from voice.session import CallSession

    class DummyWebSocket:
        def __init__(self):
            self.messages = []

        async def send_text(self, message):
            self.messages.append(json.loads(message))

    async def run_test():
        session = CallSession()
        session.stream_sid = "STREAM001"
        session.speaking = True
        session.playback_mark_name = "tts-1"
        websocket = DummyWebSocket()

        await session.cancel_speak(websocket, clear_buffer=True)

        assert session.speaking is False
        assert session.playback_mark_name is None
        assert websocket.messages == [{"event": "clear", "streamSid": "STREAM001"}]

    asyncio.run(run_test())


def test_incoming_call_passes_caller_phone_to_stream(monkeypatch):
    from voice.server import incoming_call

    class DummyRequest:
        headers = {"host": "ignored.example.com"}

        async def body(self):
            return b"From=%2B14805551234"

    monkeypatch.setenv("PUBLIC_HOST", "clinic.example.ngrok-free.app")

    response = asyncio.run(incoming_call(DummyRequest()))
    twiml = response.body.decode("utf-8")

    assert 'url="wss://clinic.example.ngrok-free.app/voice-stream"' in twiml
    assert '<Parameter name="caller_phone" value="+14805551234" />' in twiml


def test_session_process_turn_survives_langgraph_base_exception():
    from voice.session import CallSession

    class PanicLike(BaseException):
        pass

    graph = MagicMock()
    graph.invoke.side_effect = PanicLike("native panic")

    session = CallSession()
    session.call_sid = "CALL001"
    session.stream_sid = "STREAM001"
    session.caller_phone = "unknown"
    session.init_state()

    with patch("voice.session.get_compiled_graph", return_value=graph):
        response = asyncio.run(session.process_turn("What are your hours?"))

    assert "technical issue" in response
    assert session.state["conversation_history"][-1]["role"] == "agent"
