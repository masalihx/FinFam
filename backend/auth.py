"""Accounts, sessions and family rooms."""
import hashlib
import hmac
import re
import secrets
from datetime import datetime

from fastapi import HTTPException, Request

from backend import db

PBKDF2_ROUNDS = 200_000
COOKIE = "fp_session"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def hash_password(password: str, salt: str = None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ROUNDS).hex()
    return digest, salt


def check_password(password: str, digest: str, salt: str) -> bool:
    return hmac.compare_digest(hash_password(password, salt)[0], digest)


def create_user(conn, email: str, name: str, password: str) -> int:
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "Please enter a valid email.")
    if len(password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters.")
    if db.one(conn, "SELECT id FROM users WHERE email = ?", (email,)):
        raise HTTPException(409, "An account with this email already exists. Log in instead.")
    digest, salt = hash_password(password)
    cur = conn.execute("INSERT INTO users(email, name, password_hash, salt, created_at) VALUES (?, ?, ?, ?, ?)",
                       (email, name.strip() or email.split("@")[0], digest, salt, datetime.now().isoformat()))
    return cur.lastrowid


def login(conn, email: str, password: str) -> int:
    u = db.one(conn, "SELECT * FROM users WHERE email = ?", (email.strip().lower(),))
    if not u or not check_password(password, u["password_hash"], u["salt"]):
        raise HTTPException(401, "Wrong email or password.")
    return u["id"]


def new_session(conn, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    conn.execute("INSERT INTO sessions(token, user_id, created_at) VALUES (?, ?, ?)",
                 (token, user_id, datetime.now().isoformat()))
    return token


def room_code(name: str) -> str:
    word = re.sub(r"[^A-Z]", "", name.upper().replace("FAMILY", "").replace("THE", ""))[:6] or "FAMILY"
    return f"{word}-{secrets.randbelow(9000) + 1000}"


def create_room(conn, user_id: int, name: str, display_name: str) -> dict:
    for _ in range(10):
        code = room_code(name)
        if not db.one(conn, "SELECT id FROM rooms WHERE code = ?", (code,)):
            break
    cur = conn.execute("INSERT INTO rooms(name, code, created_by, created_at) VALUES (?, ?, ?, ?)",
                       (name.strip() or "Our family", code, user_id, datetime.now().isoformat()))
    room_id = cur.lastrowid
    conn.execute("INSERT INTO members(room_id, user_id, role, display_name) VALUES (?, ?, 'parent', ?)",
                 (room_id, user_id, display_name))
    return {"room_id": room_id, "code": code}


def join_room(conn, user_id: int, code: str, role: str, display_name: str) -> int:
    room = db.one(conn, "SELECT * FROM rooms WHERE code = ?", (code.strip().upper(),))
    if not room:
        raise HTTPException(404, "No family room with this code. Check the code with your parent.")
    if role not in ("parent", "teen"):
        raise HTTPException(400, "Role must be parent or teen.")
    if db.one(conn, "SELECT id FROM members WHERE room_id = ? AND user_id = ?", (room["id"], user_id)):
        return room["id"]
    conn.execute("INSERT INTO members(room_id, user_id, role, display_name) VALUES (?, ?, ?, ?)",
                 (room["id"], user_id, role, display_name))
    return room["id"]


def token_from(request: Request):
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.cookies.get(COOKIE)


def current(request: Request, need_room: bool = True) -> dict:
    """The signed-in user and (optionally) their family room membership."""
    token = token_from(request)
    with db.session() as conn:
        s = db.one(conn, "SELECT * FROM sessions WHERE token = ?", (token,)) if token else None
        if not s:
            raise HTTPException(401, "Please log in.")
        user = db.one(conn, "SELECT id, email, name FROM users WHERE id = ?", (s["user_id"],))
        member = db.one(conn, "SELECT m.*, r.name AS room_name, r.code AS room_code, r.setup_done, r.is_demo "
                              "FROM members m JOIN rooms r ON r.id = m.room_id WHERE m.user_id = ? "
                              "ORDER BY m.id LIMIT 1", (user["id"],))
    if need_room and not member:
        raise HTTPException(409, "Create a family room or join one with an invite code first.")
    return {"user": user, "member": member, "token": token}


def require_parent(ctx: dict) -> None:
    if ctx["member"]["role"] != "parent":
        raise HTTPException(403, "Only parents can do this.")
