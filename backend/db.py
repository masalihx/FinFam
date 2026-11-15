"""SQLite storage: the platform's memory about the family."""
import sqlite3
from contextlib import contextmanager

from backend.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    amount REAL NOT NULL,
    description TEXT NOT NULL,
    merchant TEXT,
    channel TEXT,
    category TEXT,
    category_source TEXT,      -- model | user
    source TEXT NOT NULL       -- demo | paypal
);
CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(date);

CREATE TABLE IF NOT EXISTS corrections (
    merchant_key TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    example TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    target REAL NOT NULL,
    saved REAL NOT NULL DEFAULT 0,
    deadline TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS budgets (
    category TEXT PRIMARY KEY,
    amount REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS postponed (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    price REAL NOT NULL,
    url TEXT,
    category TEXT,
    probability REAL,
    created_at TEXT NOT NULL,
    remind_on TEXT,
    status TEXT NOT NULL DEFAULT 'waiting'   -- waiting | bought | dropped
);

CREATE TABLE IF NOT EXISTS profile (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def session():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init() -> None:
    with session() as conn:
        conn.executescript(SCHEMA)


def get_profile(conn) -> dict:
    return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM profile")}


def set_profile(conn, **values) -> None:
    conn.executemany("INSERT OR REPLACE INTO profile(key, value) VALUES (?, ?)",
                     [(k, None if v is None else str(v)) for k, v in values.items()])


def rows(conn, sql: str, params=()) -> list:
    return [dict(r) for r in conn.execute(sql, params)]
