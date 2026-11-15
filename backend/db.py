"""SQLite storage: users, family rooms and the room's money memory."""
import sqlite3
from contextlib import contextmanager

from backend.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    code TEXT NOT NULL UNIQUE,
    created_by INTEGER NOT NULL REFERENCES users(id),
    setup_done INTEGER NOT NULL DEFAULT 0,
    is_demo INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER NOT NULL REFERENCES rooms(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    role TEXT NOT NULL,                 -- parent | teen
    display_name TEXT NOT NULL,
    paypal_email TEXT,
    allowance_amount REAL,
    allowance_period TEXT,              -- week | month
    UNIQUE(room_id, user_id)
);
CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    room_id INTEGER NOT NULL REFERENCES rooms(id),
    member_id INTEGER REFERENCES members(id),
    date TEXT NOT NULL,
    amount REAL NOT NULL,
    description TEXT NOT NULL,
    merchant TEXT,
    channel TEXT,
    category TEXT,
    category_source TEXT,               -- model | user | file
    source TEXT NOT NULL                -- demo | paypal | upload | manual | allowance
);
CREATE INDEX IF NOT EXISTS idx_tx_room_date ON transactions(room_id, date);
CREATE TABLE IF NOT EXISTS corrections (
    room_id INTEGER NOT NULL,
    merchant_key TEXT NOT NULL,
    category TEXT NOT NULL,
    example TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (room_id, merchant_key)
);
CREATE TABLE IF NOT EXISTS needs_wants (
    room_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    kind TEXT NOT NULL,                 -- need | want
    monthly_limit REAL,
    PRIMARY KEY (room_id, category)
);
CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER NOT NULL,
    member_id INTEGER,                  -- NULL = family goal
    name TEXT NOT NULL,
    target REAL NOT NULL,
    saved REAL NOT NULL DEFAULT 0,
    deadline TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER NOT NULL,
    member_id INTEGER,
    name TEXT NOT NULL,
    amount REAL NOT NULL,
    date TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS postponed (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER NOT NULL,
    member_id INTEGER,
    title TEXT NOT NULL,
    price REAL NOT NULL,
    url TEXT,
    category TEXT,
    decision TEXT,
    probability REAL,
    created_at TEXT NOT NULL,
    remind_on TEXT,
    status TEXT NOT NULL DEFAULT 'waiting'   -- waiting | bought | dropped
);
CREATE TABLE IF NOT EXISTS uploads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER NOT NULL,
    member_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    kind TEXT NOT NULL,
    rows_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'preview',  -- preview | imported | discarded
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS price_cache (
    title TEXT PRIMARY KEY,
    gemini_price REAL,
    created_at TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
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


def rows(conn, sql: str, params=()) -> list:
    return [dict(r) for r in conn.execute(sql, params)]


def one(conn, sql: str, params=()):
    r = conn.execute(sql, params).fetchone()
    return dict(r) if r else None
