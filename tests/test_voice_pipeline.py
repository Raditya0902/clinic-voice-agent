"""Smoke tests for the refactored voice pipeline modules."""
import importlib

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
