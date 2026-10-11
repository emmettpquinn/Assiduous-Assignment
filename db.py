"""SQLite storage: one table of financial facts (period, item, value, source page, how it was obtained)."""
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent
DB_PATH = ROOT / "board_report.db"
SEED_PATH = ROOT / "data" / "financials.json"

SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    period  TEXT NOT NULL,
    item    TEXT NOT NULL,
    value   REAL NOT NULL,
    page    INTEGER,
    method  TEXT NOT NULL,          -- 'verified' (hand-checked seed) or 'ai' (extract.py)
    PRIMARY KEY (period, item)
);
"""


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    return conn


def load_seed():
    return json.loads(SEED_PATH.read_text(encoding="utf-8"))


def seed_if_empty():
    """Fill the database from data/financials.json the first time the app runs."""
    with connect() as conn:
        if conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]:
            return
        for period, items in load_seed()["facts"].items():
            for item, (value, page) in items.items():
                conn.execute("INSERT INTO facts VALUES (?, ?, ?, ?, 'verified')", (period, item, value, page))


def save_facts(rows, method):
    """rows: iterable of (period, item, value, page). Overwrites existing values."""
    with connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO facts VALUES (?, ?, ?, ?, ?)",
            [(p, i, v, pg, method) for p, i, v, pg in rows],
        )


def get_facts():
    """Returns {period: {item: value}} plus {(period, item): (page, method)} for source links."""
    seed_if_empty()
    facts, sources = {}, {}
    with connect() as conn:
        for r in conn.execute("SELECT * FROM facts"):
            facts.setdefault(r["period"], {})[r["item"]] = r["value"]
            sources[(r["period"], r["item"])] = (r["page"], r["method"])
    return facts, sources
