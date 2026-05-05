import sqlite3
import os

DB_PATH = os.environ.get("DB_PATH", "./clinic.db")


def get_all_doctors(db_path: str = DB_PATH) -> list[dict]:
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT id, name, specialty FROM doctors ORDER BY id"
    ).fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "specialty": r[2]} for r in rows]


def find_doctor_by_name(name_fragment: str, db_path: str = DB_PATH) -> dict | None:
    """Case-insensitive partial name match. Returns first hit."""
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT id, name, specialty FROM doctors WHERE LOWER(name) LIKE LOWER(?)",
        (f"%{name_fragment}%",),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {"id": row[0], "name": row[1], "specialty": row[2]}
