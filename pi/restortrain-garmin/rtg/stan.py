"""Stan synchronizacji: SQLite data/state.db (treningi i przebiegi)."""
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "state.db"


def baza():
    DB.parent.mkdir(exist_ok=True)
    db = sqlite3.connect(DB)
    db.executescript("""
    CREATE TABLE IF NOT EXISTS treningi (
      source_workout_id TEXT NOT NULL, date TEXT NOT NULL, description_hash TEXT, generated_workout_id TEXT,
      generated_schedule_id TEXT, source_schedule_id TEXT, title TEXT, status TEXT, updated_at TEXT,
      PRIMARY KEY (source_workout_id, date));
    CREATE TABLE IF NOT EXISTS przebiegi (t TEXT, wynik TEXT, opis TEXT);
    """)
    return db


def drukuj_status():
    db = baza()
    print("Ostatnie przebiegi:")
    for t, w, o in db.execute("SELECT t, wynik, opis FROM przebiegi ORDER BY t DESC LIMIT 10"):
        print(f"  {t} {w} {o or ''}")
    print("Treningi:")
    for r in db.execute("SELECT date, title, status, source_workout_id, generated_workout_id FROM treningi ORDER BY date"):
        print("  " + " · ".join(str(x) for x in r))
