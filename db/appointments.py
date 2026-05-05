import sqlite3
import os
from datetime import datetime, timezone

DB_PATH = os.environ.get("DB_PATH", "./clinic.db")


def get_patient_appointments(patient_id: int, db_path: str = DB_PATH) -> list[dict]:
    """Return upcoming confirmed appointments for a patient, ordered by date/time."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT a.id, d.id as doctor_id, d.name, a.date, a.start_time, a.reason "
        "FROM appointments a JOIN doctors d ON a.doctor_id = d.id "
        "WHERE a.patient_id = ? AND a.status = 'confirmed' AND a.date >= ? "
        "ORDER BY a.date, a.start_time",
        (patient_id, today),
    ).fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "doctor_id": r[1],
            "doctor_name": r[2],
            "date": r[3],
            "start_time": r[4],
            "reason": r[5],
        }
        for r in rows
    ]
