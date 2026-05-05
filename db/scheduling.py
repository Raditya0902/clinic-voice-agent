import sqlite3
from datetime import datetime, timedelta, timezone
import os

DB_PATH = os.environ.get("DB_PATH", "./clinic.db")
LOCK_TIMEOUT_SECONDS = int(os.environ.get("SLOT_LOCK_TIMEOUT", "60"))


def get_available_slots(doctor_id: int, date: str, db_path: str = DB_PATH) -> list[dict]:
    """Return open slots for a doctor on a given date (ISO format: YYYY-MM-DD)."""
    conn = sqlite3.connect(db_path)
    now = datetime.now(timezone.utc).isoformat()
    rows = conn.execute(
        "SELECT id, start_time, end_time FROM slots "
        "WHERE doctor_id = ? AND date = ? AND is_available = 1 "
        "AND (locked_until IS NULL OR locked_until < ?) "
        "ORDER BY start_time",
        (doctor_id, date, now),
    ).fetchall()
    conn.close()
    return [{"slot_id": r[0], "start_time": r[1], "end_time": r[2]} for r in rows]


def lock_slot(slot_id: int, call_sid: str, db_path: str = DB_PATH) -> bool:
    """
    Attempt an optimistic lock on a slot for this call.
    Returns True if the lock was acquired, False if already locked/taken.
    The lock expires after LOCK_TIMEOUT_SECONDS (default 60 s).
    """
    conn = sqlite3.connect(db_path)
    now = datetime.now(timezone.utc).isoformat()
    expiry = (datetime.now(timezone.utc) + timedelta(seconds=LOCK_TIMEOUT_SECONDS)).isoformat()

    conn.execute(
        "UPDATE slots SET locked_until = NULL, locked_by = NULL "
        "WHERE locked_until IS NOT NULL AND locked_until < ?",
        (now,),
    )

    cursor = conn.execute(
        "UPDATE slots SET locked_until = ?, locked_by = ? "
        "WHERE id = ? AND is_available = 1 "
        "AND (locked_until IS NULL OR locked_until < ? OR locked_by = ?)",
        (expiry, call_sid, slot_id, now, call_sid),
    )
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success


def confirm_booking(
    slot_id: int, call_sid: str, patient_id: int, reason: str, db_path: str = DB_PATH
) -> int:
    """
    Convert a locked slot into a confirmed appointment.
    Raises if this call does not hold the lock.
    Returns the new appointment_id.
    """
    conn = sqlite3.connect(db_path)

    row = conn.execute(
        "SELECT doctor_id, date, start_time FROM slots WHERE id = ? AND locked_by = ?",
        (slot_id, call_sid),
    ).fetchone()
    if not row:
        conn.close()
        raise RuntimeError(f"Slot {slot_id} not locked by call {call_sid}")

    doctor_id, date, start_time = row
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        "UPDATE slots SET is_available = 0, locked_until = NULL, locked_by = NULL WHERE id = ?",
        (slot_id,),
    )
    cursor = conn.execute(
        "INSERT INTO appointments "
        "(patient_id, slot_id, doctor_id, date, start_time, reason, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'confirmed', ?)",
        (patient_id, slot_id, doctor_id, date, start_time, reason, now),
    )
    conn.commit()
    appointment_id = cursor.lastrowid
    conn.close()
    return appointment_id


def release_slot(slot_id: int, call_sid: str, db_path: str = DB_PATH) -> None:
    """Release a lock held by this call (e.g. on call end without confirming)."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE slots SET locked_until = NULL, locked_by = NULL "
        "WHERE id = ? AND locked_by = ?",
        (slot_id, call_sid),
    )
    conn.commit()
    conn.close()


def cancel_appointment(appointment_id: int, db_path: str = DB_PATH) -> None:
    """Mark an appointment cancelled and free its slot."""
    conn = sqlite3.connect(db_path)
    now = datetime.now(timezone.utc).isoformat()

    row = conn.execute(
        "SELECT slot_id FROM appointments WHERE id = ?", (appointment_id,)
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE slots SET is_available = 1 WHERE id = ?", (row[0],)
        )
    conn.execute(
        "UPDATE appointments SET status = 'cancelled', updated_at = ? WHERE id = ?",
        (now, appointment_id),
    )
    conn.commit()
    conn.close()
