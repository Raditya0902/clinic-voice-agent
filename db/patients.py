import sqlite3
import os

DB_PATH = os.environ.get("DB_PATH", "./clinic.db")


def lookup_patient(full_name: str, date_of_birth: str, db_path: str = DB_PATH) -> dict | None:
    """
    Match a patient by full name and date of birth (YYYY-MM-DD).
    Returns a dict with patient fields or None if not found.
    """
    parts = full_name.strip().split(None, 1)
    first = parts[0] if parts else ""
    last = parts[1] if len(parts) > 1 else ""

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT id, first_name, last_name, date_of_birth, phone, email FROM patients "
        "WHERE LOWER(first_name) = LOWER(?) AND LOWER(last_name) = LOWER(?) "
        "AND date_of_birth = ?",
        (first, last, date_of_birth),
    ).fetchone()
    conn.close()

    if not row:
        return None
    return {
        "id": row[0],
        "first_name": row[1],
        "last_name": row[2],
        "date_of_birth": row[3],
        "phone": row[4],
        "email": row[5],
    }


def get_patient_by_id(patient_id: int, db_path: str = DB_PATH) -> dict | None:
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT id, first_name, last_name, date_of_birth, phone, email FROM patients WHERE id = ?",
        (patient_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row[0],
        "first_name": row[1],
        "last_name": row[2],
        "date_of_birth": row[3],
        "phone": row[4],
        "email": row[5],
    }
