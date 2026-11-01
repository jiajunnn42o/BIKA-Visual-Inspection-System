"""Authenticated Data Analytics date-range preferences, scoped by User.id.

Standalone SQLite storage under Flask instance_path avoids altering existing
model tables or requiring an Alembic migration for this small UI preference.
On multiple web servers, use a shared application DB instead.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path
from flask import current_app

PERIODS = {"today", "7d", "30d", "90d", "all", "custom"}
DB_NAME = "analytics_period_preferences.sqlite3"


def _connection():
    db_file = Path(current_app.instance_path) / DB_NAME
    db_file.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(db_file), timeout=6)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout = 6000")
    db.execute("""CREATE TABLE IF NOT EXISTS analytics_period_preferences (
       user_id INTEGER PRIMARY KEY,
       range_key TEXT NOT NULL,
       date_from TEXT,
       date_to TEXT,
       updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    return db


def validate_preference(payload):
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object")
    period = payload.get("range")
    if period not in PERIODS:
        raise ValueError("Invalid Analytics period")
    if period == "custom":
        begin, end = payload.get("from"), payload.get("to")
        if not isinstance(begin, str) or not isinstance(end, str):
            raise ValueError("Both custom dates are required")
        if len(begin) != 10 or len(end) != 10:
            raise ValueError("Dates must be ISO-8601 (YYYY-MM-DD)")
        try:
            a, b = date.fromisoformat(begin), date.fromisoformat(end)
        except ValueError as exc:
            raise ValueError("Invalid date") from exc
        if a.isoformat() != begin or b.isoformat() != end or a > b:
            raise ValueError("Invalid custom date range")
        return {"range": period, "from": begin, "to": end}
    return {"range": period, "from": None, "to": None}


def get_period_preference(user_id):
    with closing(_connection()) as db:
        row = db.execute(
            "SELECT range_key, date_from, date_to FROM analytics_period_preferences WHERE user_id=?",
            (int(user_id),)
        ).fetchone()
    if row is None:
        return None
    return validate_preference({"range": row["range_key"], "from": row["date_from"], "to": row["date_to"]})


def save_period_preference(user_id, payload):
    value = validate_preference(payload)
    with closing(_connection()) as db:
        db.execute("""INSERT INTO analytics_period_preferences (user_id, range_key, date_from, date_to)
          VALUES (?, ?, ?, ?)
          ON CONFLICT(user_id) DO UPDATE SET
          range_key=excluded.range_key, date_from=excluded.date_from,
          date_to=excluded.date_to, updated_at=CURRENT_TIMESTAMP""",
          (int(user_id), value["range"], value["from"], value["to"])
        )
        db.commit()
    return value
