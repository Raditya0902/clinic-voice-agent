import sqlite3
import json
import os
from datetime import datetime, timezone

DB_PATH = os.environ.get("DB_PATH", "./clinic.db")


def start_call_record(call_sid: str, caller_phone: str, db_path: str = DB_PATH) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO call_history "
        "(call_sid, caller_phone, start_time, created_at) VALUES (?, ?, ?, ?)",
        (call_sid, caller_phone, now, now),
    )
    conn.commit()
    conn.close()


def end_call_record(
    call_sid: str,
    *,
    transcript: list[dict] | None = None,
    intent_sequence: list[str] | None = None,
    outcome: str | None = None,
    appointment_id: int | None = None,
    patient_id: int | None = None,
    sentiment_avg: float | None = None,
    total_tokens: int | None = None,
    escalated: bool = False,
    call_summary: str | None = None,
    db_path: str = DB_PATH,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db_path)
    start_row = conn.execute(
        "SELECT start_time FROM call_history WHERE call_sid = ?", (call_sid,)
    ).fetchone()
    duration = None
    if start_row:
        try:
            start_dt = datetime.fromisoformat(start_row[0])
            duration = int((datetime.now(timezone.utc) - start_dt).total_seconds())
        except Exception:
            pass

    conn.execute(
        "UPDATE call_history SET "
        "end_time = ?, duration_seconds = ?, transcript = ?, intent_sequence = ?, "
        "outcome = ?, appointment_id = ?, patient_id = ?, sentiment_avg = ?, "
        "total_tokens = ?, escalated = ?, call_summary = ? "
        "WHERE call_sid = ?",
        (
            now,
            duration,
            json.dumps(transcript) if transcript else None,
            json.dumps(intent_sequence) if intent_sequence else None,
            outcome,
            appointment_id,
            patient_id,
            sentiment_avg,
            total_tokens,
            escalated,
            call_summary,
            call_sid,
        ),
    )
    conn.commit()
    conn.close()


def get_recent_calls(limit: int = 50, db_path: str = DB_PATH) -> list[dict]:
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT call_sid, caller_phone, start_time, end_time, duration_seconds, "
        "outcome, escalated, call_summary, transcript, intent_sequence, sentiment_avg "
        "FROM call_history ORDER BY start_time DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [
        {
            "call_sid": r[0],
            "caller_phone": r[1],
            "start_time": r[2],
            "end_time": r[3],
            "duration_seconds": r[4],
            "outcome": r[5],
            "escalated": bool(r[6]),
            "call_summary": r[7],
            "transcript": json.loads(r[8]) if r[8] else [],
            "intent_sequence": json.loads(r[9]) if r[9] else [],
            "sentiment_avg": r[10],
        }
        for r in rows
    ]


def get_dashboard_stats(db_path: str = DB_PATH) -> dict:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn = sqlite3.connect(db_path)

    active = conn.execute(
        "SELECT COUNT(*) FROM call_history WHERE end_time IS NULL"
    ).fetchone()[0]

    today_total = conn.execute(
        "SELECT COUNT(*) FROM call_history WHERE start_time LIKE ?",
        (f"{today}%",),
    ).fetchone()[0]

    completed = conn.execute(
        "SELECT COUNT(*) FROM call_history WHERE end_time IS NOT NULL"
    ).fetchone()[0]

    successful = conn.execute(
        "SELECT COUNT(*) FROM call_history "
        "WHERE outcome IN ('booked', 'cancelled') AND end_time IS NOT NULL"
    ).fetchone()[0]

    avg_dur = conn.execute(
        "SELECT AVG(duration_seconds) FROM call_history WHERE duration_seconds IS NOT NULL"
    ).fetchone()[0] or 0.0

    conn.close()

    return {
        "active_count": active,
        "today_count": today_total,
        "success_rate": (successful / completed) if completed > 0 else 0.0,
        "avg_duration_s": avg_dur,
    }
