import sqlite3
import os

DB_PATH = os.environ.get("DB_PATH", "./clinic.db")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS doctors (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    specialty TEXT NOT NULL,
    available_days TEXT NOT NULL,
    slot_duration_minutes INTEGER DEFAULT 30
);

CREATE TABLE IF NOT EXISTS slots (
    id INTEGER PRIMARY KEY,
    doctor_id INTEGER REFERENCES doctors(id),
    date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    is_available BOOLEAN DEFAULT TRUE,
    locked_until TEXT DEFAULT NULL,
    locked_by TEXT DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    date_of_birth TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY,
    patient_id INTEGER REFERENCES patients(id),
    slot_id INTEGER REFERENCES slots(id),
    doctor_id INTEGER REFERENCES doctors(id),
    date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    reason TEXT,
    status TEXT DEFAULT 'confirmed',
    created_at TEXT NOT NULL,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS call_history (
    id INTEGER PRIMARY KEY,
    call_sid TEXT NOT NULL,
    caller_phone TEXT NOT NULL,
    patient_id INTEGER REFERENCES patients(id),
    start_time TEXT NOT NULL,
    end_time TEXT,
    duration_seconds INTEGER,
    transcript TEXT,
    intent_sequence TEXT,
    outcome TEXT,
    appointment_id INTEGER REFERENCES appointments(id),
    sentiment_avg REAL,
    total_tokens INTEGER,
    total_cost_usd REAL,
    escalated BOOLEAN DEFAULT FALSE,
    call_summary TEXT,
    created_at TEXT NOT NULL
);
"""


def create_tables(db_path: str = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()
