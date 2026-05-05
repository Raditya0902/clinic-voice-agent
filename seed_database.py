"""Populate clinic.db with demo doctors, slots, and patients.

Run once after creating the DB schema:
    python seed_database.py
"""
import sqlite3
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os

load_dotenv()

from db.models import create_tables, DB_PATH


def seed(db_path: str = DB_PATH) -> None:
    create_tables(db_path)
    conn = sqlite3.connect(db_path)

    # Doctors
    doctors = [
        (1, "Dr. Sarah Smith", "General Practice", "Mon,Tue,Wed,Thu,Fri", 30),
        (2, "Dr. Raj Patel", "Internal Medicine", "Mon,Tue,Wed,Thu", 30),
        (3, "Dr. Emily Johnson", "Pediatrics", "Mon,Wed,Fri", 30),
        (4, "Dr. Michael Chen", "Dermatology", "Tue,Thu", 45),
    ]
    conn.executemany(
        "INSERT OR IGNORE INTO doctors (id, name, specialty, available_days, slot_duration_minutes) "
        "VALUES (?,?,?,?,?)",
        doctors,
    )

    # Patients
    patients = [
        (1, "John", "Doe", "1990-03-05", "4805551234", "john@email.com"),
        (2, "Jane", "Roe", "1985-07-22", "4805555678", "jane@email.com"),
        (3, "Aditya", "Rallapalli", "1998-01-15", "4805559012", "aditya@email.com"),
        (4, "Maria", "Garcia", "1975-11-30", "4805553456", "maria@email.com"),
    ]
    conn.executemany(
        "INSERT OR IGNORE INTO patients (id, first_name, last_name, date_of_birth, phone, email, created_at) "
        "VALUES (?,?,?,?,?,?, datetime('now'))",
        patients,
    )

    # Clear existing slots so re-running doesn't create duplicates
    conn.execute("DELETE FROM slots")
    conn.commit()

    # Slots — next 14 days
    today = datetime.now().date()

    for doctor_id, _, _, available_days, duration in doctors:
        avail = set(available_days.split(","))
        for offset in range(14):
            date = today + timedelta(days=offset)
            if date.strftime("%a") not in avail:
                continue
            hour = 8
            while hour < 17:
                start = f"{hour:02d}:00"
                end_hour = hour + duration // 60
                end_min = duration % 60
                end = f"{end_hour:02d}:{end_min:02d}"
                conn.execute(
                    "INSERT INTO slots (doctor_id, date, start_time, end_time, is_available) "
                    "VALUES (?, ?, ?, ?, 1)",
                    (doctor_id, date.isoformat(), start, end),
                )
                hour += 1 if duration <= 30 else 1

    conn.commit()

    doctor_count = conn.execute("SELECT COUNT(*) FROM doctors").fetchone()[0]
    slot_count = conn.execute("SELECT COUNT(*) FROM slots").fetchone()[0]
    patient_count = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
    conn.close()

    print(f"Seeded: {doctor_count} doctors, {slot_count} slots, {patient_count} patients")
    print(f"DB: {os.path.abspath(db_path)}")


if __name__ == "__main__":
    seed()
