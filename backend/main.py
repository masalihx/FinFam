"""FinPilot API and website.

Run from the project root:
    .venv/bin/uvicorn backend.main:app --reload --port 8000
Then open http://localhost:8000
"""
import json
import sys
from datetime import datetime
from typing import List, Optional

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend import assistant as assistant_mod
from backend import auth, db, demo, finance, gemini, ml_service, paypal
from backend.config import ROOT, WEB_DIR
from backend.finance import CATEGORY_NAMES

sys.path.insert(0, str(ROOT / "ml"))
from verdict import Signals, decide, reasonable_price  # noqa: E402

DISCLAIMER = "This project is a prototype and is not financial advice."
MARKET_CATEGORIES = {"shopping", "personal_care", "health", "education_childcare", "groceries"}
MAX_UPLOAD_BYTES = 15 * 1024 * 1024

app = FastAPI(title="FinPilot", description=DISCLAIMER)
# The Chrome extension calls the API from shop pages with a Bearer token; everything runs locally.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

categorizer = ml_service.Categorizer()
overspend = ml_service.OverspendModel()
prices = ml_service.PriceModel()
recurring = ml_service.RecurringModel()
assistant = assistant_mod.Assistant()
db.init()


# ---------------------------------------------------------------- helpers

def ctx_of(request: Request, need_room: bool = True) -> dict:
    return auth.current(request, need_room)


def room_members(conn, room_id: int) -> list:
    return db.rows(conn, "SELECT m.id, m.role, m.display_name, m.paypal_email, m.allowance_amount, m.allowance_period, "
                         "u.email FROM members m JOIN users u ON u.id = m.user_id WHERE m.room_id = ? ORDER BY m.id",
                   (room_id,))


def load_room(conn, room_id: int) -> dict:
    df = finance.tx_frame(db.rows(conn, "SELECT * FROM transactions WHERE room_id = ? ORDER BY date", (room_id,)))
    limits = {r["category"]: r["monthly_limit"] for r in db.rows(
        conn, "SELECT * FROM needs_wants WHERE room_id = ? AND kind = 'want' AND monthly_limit IS NOT NULL", (room_id,))}
    kinds = {r["category"]: r["kind"] for r in db.rows(conn, "SELECT * FROM needs_wants WHERE room_id = ?", (room_id,))}
    goals = db.rows(conn, "SELECT * FROM goals WHERE room_id = ? ORDER BY deadline", (room_id,))
    return {"df": df, "limits": limits, "kinds": kinds, "goals": goals, "members": room_members(conn, room_id)}


def family_state(room: dict, today):
    teens = sum(1 for m in room["members"] if m["role"] == "teen")
    return ml_service.family_state(room["df"], ml_service.yearly_income(room["df"], today), teens)


def require_data(room: dict):
    if room["df"].empty:
        raise HTTPException(409, "No transactions yet. Connect PayPal, upload a statement or load the demo family.")


def corrections_map(conn, room_id: int) -> dict:
    return {r["merchant_key"]: r["category"] for r in
            db.rows(conn, "SELECT * FROM corrections WHERE room_id = ?", (room_id,))}


def insert_transactions(conn, room_id: int, member_id: int, items: list, source: str) -> int:
    texts = [ml_service.with_sign(t["amount"], t["description"]) for t in items]
    cats = categorizer.predict(texts, corrections_map(conn, room_id))
    conn.executemany(
        "INSERT OR REPLACE INTO transactions(id, room_id, member_id, date, amount, description, merchant, channel, "
        "category, category_source, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(t["id"], room_id, t.get("member_id", member_id), t["date"], t["amount"], t["description"], t.get("merchant"),
          t.get("channel"), t.get("category") or c, "file" if t.get("category") else "model", source)
         for t, c in zip(items, cats)])
    return len(items)


def set_cookie(response: Response, token: str):
    response.set_cookie(auth.COOKIE, token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 30)


def me_payload(ctx: dict) -> dict:
    m = ctx["member"]
    out = {"user": ctx["user"], "member": None, "token": ctx["token"]}
    if m:
        out["member"] = {"id": m["id"], "role": m["role"], "display_name": m["display_name"],
                         "room_id": m["room_id"], "room_name": m["room_name"], "room_code": m["room_code"],
                         "setup_done": bool(m["setup_done"]), "is_demo": bool(m["is_demo"])}
    return out


def names_of(room: dict) -> dict:
    return {m["id"]: m["display_name"] for m in room["members"]}


# ---------------------------------------------------------------- accounts and rooms

class RegisterIn(BaseModel):
    email: str
    name: str = ""
    password: str


class LoginIn(BaseModel):
    email: str
    password: str


class RoomIn(BaseModel):
    name: str


class JoinIn(BaseModel):
    code: str
    role: str = "teen"


@app.post("/api/auth/register")
def register(body: RegisterIn, response: Response):
    with db.session() as conn:
        uid = auth.create_user(conn, body.email, body.name, body.password)
        token = auth.new_session(conn, uid)
    set_cookie(response, token)
    return {"token": token}


@app.post("/api/auth/login")
def login(body: LoginIn, response: Response):
    with db.session() as conn:
        uid = auth.login(conn, body.email, body.password)
        token = auth.new_session(conn, uid)
    set_cookie(response, token)
    return {"token": token}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    token = auth.token_from(request)
    if token:
        with db.session() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
    response.delete_cookie(auth.COOKIE)
    return {"ok": True}


@app.get("/api/me")
def me(request: Request):
    return me_payload(ctx_of(request, need_room=False))


@app.post("/api/rooms")
def create_room(body: RoomIn, request: Request):
    ctx = ctx_of(request, need_room=False)
    if ctx["member"]:
        raise HTTPException(409, "You are already in a family room.")
    with db.session() as conn:
        return auth.create_room(conn, ctx["user"]["id"], body.name, ctx["user"]["name"])


@app.post("/api/rooms/join")
def join_room(body: JoinIn, request: Request):
    ctx = ctx_of(request, need_room=False)
    if ctx["member"]:
        raise HTTPException(409, "You are already in a family room.")
    with db.session() as conn:
        return {"room_id": auth.join_room(conn, ctx["user"]["id"], body.code, body.role, ctx["user"]["name"])}


@app.get("/api/room")
def room_info(request: Request):
    ctx = ctx_of(request)
    with db.session() as conn:
        members = room_members(conn, ctx["member"]["room_id"])
        counts = {r["member_id"]: r["n"] for r in db.rows(
            conn, "SELECT member_id, COUNT(*) AS n FROM transactions WHERE room_id = ? GROUP BY member_id",
            (ctx["member"]["room_id"],))}
    for m in members:
        m["transactions"] = counts.get(m["id"], 0)
    return {**me_payload(ctx)["member"], "members": members, "paypal_configured": paypal.configured(),
            "gemini_configured": gemini.configured(), "disclaimer": DISCLAIMER}


class MemberIn(BaseModel):
    paypal_email: Optional[str] = None
    allowance_amount: Optional[float] = Field(None, ge=0)
    allowance_period: Optional[str] = None


@app.put("/api/members/{member_id}")
def update_member(member_id: int, body: MemberIn, request: Request):
    ctx = ctx_of(request)
    is_self = member_id == ctx["member"]["id"]
    with db.session() as conn:
        target = db.one(conn, "SELECT * FROM members WHERE id = ? AND room_id = ?", (member_id, ctx["member"]["room_id"]))
        if not target:
            raise HTTPException(404, "Member not found")
        if body.paypal_email is not None:
            if not (is_self or ctx["member"]["role"] == "parent"):
                raise HTTPException(403, "You can only change your own PayPal email.")
            conn.execute("UPDATE members SET paypal_email = ? WHERE id = ?",
                         (body.paypal_email.strip().lower() or None, member_id))
        if body.allowance_amount is not None or body.allowance_period is not None:
            auth.require_parent(ctx)
            if body.allowance_period not in (None, "week", "month"):
                raise HTTPException(400, "Allowance period must be week or month.")
            conn.execute("UPDATE members SET allowance_amount = ?, allowance_period = ? WHERE id = ?",
                         (body.allowance_amount, body.allowance_period or "week", member_id))
    return {"ok": True}


# ---------------------------------------------------------------- demo

def build_demo_room(conn, today) -> dict:
    ids = {}
    for p in demo.FAMILY:
        u = db.one(conn, "SELECT id FROM users WHERE email = ?", (p["email"],))
        ids[p["key"]] = u["id"] if u else auth.create_user(conn, p["email"], p["name"], demo.DEMO_PASSWORD)
    made = auth.create_room(conn, ids["alex"], demo.ROOM_NAME, "Alex")
    room_id = made["room_id"]
    conn.execute("UPDATE rooms SET is_demo = 1 WHERE id = ?", (room_id,))
    member = {"alex": db.one(conn, "SELECT id FROM members WHERE room_id = ? AND user_id = ?",
                             (room_id, ids["alex"]))["id"]}
    for p in demo.FAMILY[1:]:
        amount, period = p.get("allowance") or (None, None)
        cur = conn.execute("INSERT INTO members(room_id, user_id, role, display_name, allowance_amount, allowance_period) "
                           "VALUES (?, ?, ?, ?, ?, ?)", (room_id, ids[p["key"]], p["role"], p["name"].split()[0],
                                                         amount, period))
        member[p["key"]] = cur.lastrowid
    insert_transactions(conn, room_id, member["alex"], demo.family_bank(today), "demo")
    for key in ("maya", "leo"):
        items = demo.teen_transactions(key, today)
        for t in items:
            if t["description"].startswith("ALLOWANCE"):
                t["category"] = "income"
        insert_transactions(conn, room_id, member[key], items, "demo")
        conn.execute("UPDATE transactions SET source = 'allowance' WHERE room_id = ? AND member_id = ? "
                     "AND description LIKE 'ALLOWANCE%'", (room_id, member[key]))
    # Corrections the demo family already made in the app (the model's most common mistakes on their data).
    for text, category in demo.SEED_CORRECTIONS:
        apply_correction(conn, room_id, text, category)
    now = demo.now_iso()
    for g in demo.FAMILY_GOALS:
        conn.execute("INSERT INTO goals(room_id, member_id, name, target, saved, deadline, created_at) "
                     "VALUES (?, NULL, ?, ?, ?, ?, ?)", (room_id, g["name"], g["target"], g["saved"], g["deadline"], now))
    for key, goals in demo.PERSONAL_GOALS.items():
        for g in goals:
            conn.execute("INSERT INTO goals(room_id, member_id, name, target, saved, deadline, created_at) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (room_id, member[key], g["name"], g["target"], g["saved"], g["deadline"], now))
    for p in demo.PLANS:
        conn.execute("INSERT INTO plans(room_id, member_id, name, amount, date, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                     (room_id, member.get(p["member"]), p["name"], p["amount"],
                      str((today + pd.Timedelta(days=p["days_ahead"])).date()), now))
    return db.one(conn, "SELECT * FROM rooms WHERE id = ?", (room_id,))


@app.post("/api/demo/login")
def demo_login(response: Response, who: str = "alex"):
    """Create the demo room once, then log in as one of the Carters (alex, sam, maya, leo)."""
    today = ml_service.now()
    with db.session() as conn:
        room = db.one(conn, "SELECT * FROM rooms WHERE is_demo = 1") or build_demo_room(conn, today)
        person = next((p for p in demo.FAMILY if p["key"] == who), demo.FAMILY[0])
        uid = db.one(conn, "SELECT id FROM users WHERE email = ?", (person["email"],))["id"]
        token = auth.new_session(conn, uid)
    set_cookie(response, token)
    return {"token": token, "room_code": room["code"]}


@app.post("/api/demo/reset")
def demo_reset(request: Request):
    ctx = ctx_of(request)
    if not ctx["member"]["is_demo"]:
        raise HTTPException(400, "Only the demo room can be reset.")
    rid = ctx["member"]["room_id"]
    with db.session() as conn:
        for table in ("transactions", "corrections", "needs_wants", "goals", "plans", "postponed", "uploads", "members"):
            conn.execute(f"DELETE FROM {table} WHERE room_id = ?", (rid,))
        conn.execute("DELETE FROM rooms WHERE id = ?", (rid,))
    return {"ok": True}


# ---------------------------------------------------------------- setup: needs and wants

@app.get("/api/setup/suggestions")
def setup_suggestions(request: Request):
    ctx = ctx_of(request)
    today = ml_service.now()
    with db.session() as conn:
        room = load_room(conn, ctx["member"]["room_id"])
    require_data(room)
    by_cat = {}
    for r in recurring.upcoming(room["df"], today, days=400):
        if r["amount"] < 0:
            by_cat.setdefault(r["category"], []).append(r["name"])
    suggestions = finance.setup_suggestions(room["df"], by_cat, today)
    for s in suggestions:
        if s["category"] in room["kinds"]:
            s["kind"] = room["kinds"][s["category"]]
            s["suggested_limit"] = room["limits"].get(s["category"], s["suggested_limit"])
    return {"suggestions": suggestions, "setup_done": bool(ctx["member"]["setup_done"])}


class SetupItem(BaseModel):
    category: str
    kind: str
    monthly_limit: Optional[float] = Field(None, ge=0)


class SetupIn(BaseModel):
    items: List[SetupItem]


@app.post("/api/setup")
def save_setup(body: SetupIn, request: Request):
    ctx = ctx_of(request)
    auth.require_parent(ctx)
    rid = ctx["member"]["room_id"]
    with db.session() as conn:
        conn.execute("DELETE FROM needs_wants WHERE room_id = ?", (rid,))
        for it in body.items:
            if it.kind not in ("need", "want") or it.category not in CATEGORY_NAMES:
                raise HTTPException(400, f"Bad item {it.category}/{it.kind}")
            conn.execute("INSERT INTO needs_wants(room_id, category, kind, monthly_limit) VALUES (?, ?, ?, ?)",
                         (rid, it.category, it.kind, it.monthly_limit if it.kind == "want" else None))
        conn.execute("UPDATE rooms SET setup_done = 1 WHERE id = ?", (rid,))
    return {"ok": True}


# ---------------------------------------------------------------- family overview and upcoming

def upcoming_list(room, plans, today, days: int = 30) -> list:
    names = names_of(room)
    rec = [r for r in recurring.upcoming(room["df"], today, days) if r["amount"] < 0]
    items = [{"date": r["date"], "name": r["name"], "amount": r["amount"], "kind": "regular",
              "detail": f"{r['frequency']} · found by ML ({r['confidence']:.0%})",
              "category": r["category"], "member": names.get(r["member_id"])} for r in rec]
    horizon = str((today + pd.Timedelta(days=days)).date())
    items += [{"date": p["date"], "name": p["name"], "amount": -abs(p["amount"]), "kind": "plan", "id": p["id"],
               "detail": "planned by the family", "category": None, "member": names.get(p["member_id"])}
              for p in plans if p["date"] <= horizon]
    return sorted(items, key=lambda x: x["date"])


def future_plans(conn, room_id: int, today) -> list:
    return db.rows(conn, "SELECT * FROM plans WHERE room_id = ? AND date >= ? ORDER BY date", (room_id, str(today.date())))


@app.get("/api/overview")
def overview(request: Request):
    ctx = ctx_of(request)
    today = ml_service.now()
    with db.session() as conn:
        room = load_room(conn, ctx["member"]["room_id"])
        plans = future_plans(conn, ctx["member"]["room_id"], today)
    require_data(room)
    df = room["df"]
    out = finance.month_summary(df, family_state(room, today), overspend, today, room["limits"])
    out["goals"] = finance.plan_goals([g for g in room["goals"] if g["member_id"] is None],
                                      out["free_cash_per_month"], today)
    this_month = finance.spending(df[df["month"] == today.to_period("M")])
    by_member = (-this_month.groupby("member_id")["amount"].sum()).to_dict()
    out["by_member"] = [{"member_id": m["id"], "name": m["display_name"], "role": m["role"],
                         "spent": round(float(by_member.get(m["id"], 0.0)), 2)} for m in room["members"]]
    out["upcoming"] = upcoming_list(room, plans, today)
    out["disclaimer"] = DISCLAIMER
    return out


@app.get("/api/upcoming")
def upcoming(request: Request, days: int = 30):
    ctx = ctx_of(request)
    today = ml_service.now()
    with db.session() as conn:
        room = load_room(conn, ctx["member"]["room_id"])
        plans = future_plans(conn, ctx["member"]["room_id"], today)
    require_data(room)
    summary = finance.month_summary(room["df"], family_state(room, today), overspend, today, room["limits"])
    rest = [{"category": c["category"], "name": c["name"], "expected": c["expected_rest_of_month"],
             "risk": c["overspend_probability"], "light": c["light"]}
            for c in summary["categories"] if c["expected_rest_of_month"]]
    return {"items": upcoming_list(room, plans, today, days), "rest_of_month": rest, "days_left": summary["days_left"]}


class PlanIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    amount: float = Field(gt=0)
    date: str


@app.post("/api/plans")
def add_plan(body: PlanIn, request: Request):
    ctx = ctx_of(request)
    try:
        pd.Timestamp(body.date)
    except ValueError:
        raise HTTPException(400, "Date must look like 2026-12-20")
    with db.session() as conn:
        cur = conn.execute("INSERT INTO plans(room_id, member_id, name, amount, date, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                           (ctx["member"]["room_id"], ctx["member"]["id"], body.name, body.amount, body.date,
                            datetime.now().isoformat()))
    return {"id": cur.lastrowid}


@app.delete("/api/plans/{plan_id}")
def delete_plan(plan_id: int, request: Request):
    ctx = ctx_of(request)
    with db.session() as conn:
        conn.execute("DELETE FROM plans WHERE id = ? AND room_id = ?", (plan_id, ctx["member"]["room_id"]))
    return {"ok": True}


# ---------------------------------------------------------------- my space

@app.get("/api/space")
def my_space(request: Request, member_id: Optional[int] = None):
    """A member's own money: allowance, earnings, spending and personal goals (parents may view a teen's)."""
    ctx = ctx_of(request)
    today = ml_service.now()
    mid = member_id or ctx["member"]["id"]
    if mid != ctx["member"]["id"]:
        auth.require_parent(ctx)
    with db.session() as conn:
        member = db.one(conn, "SELECT * FROM members WHERE id = ? AND room_id = ?", (mid, ctx["member"]["room_id"]))
        if not member:
            raise HTTPException(404, "Member not found")
        rows = db.rows(conn, "SELECT * FROM transactions WHERE room_id = ? AND member_id = ? ORDER BY date DESC, id DESC",
                       (ctx["member"]["room_id"], mid))
        goals = db.rows(conn, "SELECT * FROM goals WHERE room_id = ? AND member_id = ?", (ctx["member"]["room_id"], mid))
    df = finance.tx_frame(rows)
    cur = today.to_period("M")
    month = df[df["month"] == cur]
    allowance = float(month.loc[month["source"] == "allowance", "amount"].clip(lower=0).sum())
    earned = float(month.loc[(month["category"] == "income") & (month["source"] != "allowance"), "amount"].sum())
    spent = float(-finance.spending(month)["amount"].sum())
    by_cat = (-finance.spending(month).groupby("category")["amount"].sum()).sort_values(ascending=False)
    last3 = df[(df["month"] < cur) & (df["month"] >= cur - 3)]
    saves = 0.0
    if len(last3):
        saves = (float(last3.loc[last3["category"] == "income", "amount"].sum())
                 - float(-finance.spending(last3)["amount"].sum())) / 3
    teen = member["role"] == "teen"
    trend = (-finance.spending(df[df["month"] >= cur - 5]).groupby("month")["amount"].sum())
    return {
        "member": {"id": member["id"], "name": member["display_name"], "role": member["role"],
                   "allowance_amount": member["allowance_amount"], "allowance_period": member["allowance_period"],
                   "paypal_email": member["paypal_email"]},
        "month": str(cur), "allowance_this_month": round(allowance, 2), "earned_this_month": round(earned, 2),
        "spent_this_month": round(spent, 2),
        "left_this_month": round(allowance + earned - spent, 2) if teen else None,
        "saves_per_month": round(saves, 2),
        "by_category": [{"category": c, "name": CATEGORY_NAMES.get(c, c), "spent": round(float(v), 2)}
                        for c, v in by_cat.items() if v > 0],
        "trend": [{"month": str(m), "spent": round(float(v), 2)} for m, v in trend.items()],
        "goals": finance.plan_goals(goals, max(0.0, saves), today),
        "recent": [{k: r[k] for k in ("id", "date", "amount", "description", "category", "source")} for r in rows[:40]],
        "note": "Personal spending also counts in the family's totals.",
    }


class IncomeIn(BaseModel):
    description: str = Field(min_length=1, max_length=80)
    amount: float = Field(gt=0)
    date: Optional[str] = None


@app.post("/api/space/income")
def add_income(body: IncomeIn, request: Request):
    """Record money a member earned: a job, gifts, selling things."""
    ctx = ctx_of(request)
    date = body.date or str(ml_service.now().date())
    tid = f"manual-{ctx['member']['id']}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    with db.session() as conn:
        insert_transactions(conn, ctx["member"]["room_id"], ctx["member"]["id"],
                            [{"id": tid, "date": date, "amount": body.amount, "description": body.description,
                              "channel": "manual", "category": "income"}], "manual")
    return {"id": tid}


class ExpenseIn(BaseModel):
    description: str = Field(min_length=1, max_length=80)
    amount: float = Field(gt=0)
    date: Optional[str] = None


@app.post("/api/space/expense")
def add_expense(body: ExpenseIn, request: Request):
    """Record a cash expense by hand; the AI picks the category."""
    ctx = ctx_of(request)
    date = body.date or str(ml_service.now().date())
    tid = f"manual-{ctx['member']['id']}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    with db.session() as conn:
        insert_transactions(conn, ctx["member"]["room_id"], ctx["member"]["id"],
                            [{"id": tid, "date": date, "amount": -body.amount, "description": body.description,
                              "channel": "manual"}], "manual")
    return {"id": tid}


class AllowanceIn(BaseModel):
    member_id: int
    via_paypal: bool = False


@app.post("/api/allowance/pay")
def pay_allowance(body: AllowanceIn, request: Request):
    """A parent pays a teen's allowance: recorded in FinPilot, optionally sent as PayPal Sandbox test money."""
    ctx = ctx_of(request)
    auth.require_parent(ctx)
    today = ml_service.now()
    with db.session() as conn:
        teen = db.one(conn, "SELECT * FROM members WHERE id = ? AND room_id = ?", (body.member_id, ctx["member"]["room_id"]))
    if not teen or teen["role"] != "teen":
        raise HTTPException(404, "Teen not found in this room.")
    if not teen["allowance_amount"]:
        raise HTTPException(400, "Set the allowance amount first.")
    payout = None
    if body.via_paypal:
        if not teen["paypal_email"]:
            raise HTTPException(400, f"Add {teen['display_name']}'s PayPal sandbox email first.")
        try:
            payout = paypal.send_allowance(teen["paypal_email"], teen["allowance_amount"],
                                           f"Allowance for {teen['display_name']}")
        except paypal.PayPalError as e:
            raise HTTPException(400, str(e))
    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    amt, channel = float(teen["allowance_amount"]), ("paypal" if payout else "internal")
    with db.session() as conn:
        conn.execute("INSERT INTO transactions(id, room_id, member_id, date, amount, description, channel, category, "
                     "category_source, source) VALUES (?, ?, ?, ?, ?, ?, ?, 'income', 'user', 'allowance')",
                     (f"allow-in-{stamp}", ctx["member"]["room_id"], teen["id"], str(today.date()), amt,
                      f"ALLOWANCE FROM {ctx['member']['display_name'].upper()}", channel))
        conn.execute("INSERT INTO transactions(id, room_id, member_id, date, amount, description, channel, category, "
                     "category_source, source) VALUES (?, ?, ?, ?, ?, ?, ?, 'transfer', 'user', 'allowance')",
                     (f"allow-out-{stamp}", ctx["member"]["room_id"], ctx["member"]["id"], str(today.date()), -amt,
                      f"ALLOWANCE TO {teen['display_name'].upper()}", channel))
    return {"ok": True, "amount": amt, "paypal": payout}


# ---------------------------------------------------------------- goals

class GoalIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    target: float = Field(gt=0)
    saved: float = Field(0, ge=0)
    deadline: str
    personal: bool = False


@app.get("/api/goals")
def list_goals(request: Request):
    ctx = ctx_of(request)
    today = ml_service.now()
    with db.session() as conn:
        room = load_room(conn, ctx["member"]["room_id"])
    free = finance.monthly_free_cash(room["df"], today) if not room["df"].empty else 0.0
    names = names_of(room)
    family = finance.plan_goals([g for g in room["goals"] if g["member_id"] is None], free, today)
    personal = [dict(finance.plan_goal(g, today), owner=names.get(g["member_id"]),
                     mine=g["member_id"] == ctx["member"]["id"]) for g in room["goals"] if g["member_id"] is not None]
    return {"family": family, "personal": personal, "free_cash_per_month": round(free, 2)}


@app.post("/api/goals")
def add_goal(goal: GoalIn, request: Request):
    ctx = ctx_of(request)
    if not goal.personal:
        auth.require_parent(ctx)
    try:
        pd.Timestamp(goal.deadline)
    except ValueError:
        raise HTTPException(400, "Deadline must be a date like 2030-09-01")
    with db.session() as conn:
        cur = conn.execute("INSERT INTO goals(room_id, member_id, name, target, saved, deadline, created_at) "
                           "VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (ctx["member"]["room_id"], ctx["member"]["id"] if goal.personal else None, goal.name,
                            goal.target, goal.saved, goal.deadline, datetime.now().isoformat()))
    return {"id": cur.lastrowid}


class SaveIn(BaseModel):
    amount: float


def editable_goal(conn, ctx, goal_id):
    g = db.one(conn, "SELECT * FROM goals WHERE id = ? AND room_id = ?", (goal_id, ctx["member"]["room_id"]))
    if not g:
        raise HTTPException(404, "Goal not found")
    parent = ctx["member"]["role"] == "parent"
    if g["member_id"] is None and not parent:
        raise HTTPException(403, "Only parents can change family goals.")
    if g["member_id"] is not None and g["member_id"] != ctx["member"]["id"] and not parent:
        raise HTTPException(403, "This is someone else's goal.")
    return g


@app.post("/api/goals/{goal_id}/save")
def add_to_goal(goal_id: int, body: SaveIn, request: Request):
    ctx = ctx_of(request)
    with db.session() as conn:
        editable_goal(conn, ctx, goal_id)
        conn.execute("UPDATE goals SET saved = MAX(0, saved + ?) WHERE id = ?", (body.amount, goal_id))
    return {"ok": True}


@app.delete("/api/goals/{goal_id}")
def delete_goal(goal_id: int, request: Request):
    ctx = ctx_of(request)
    with db.session() as conn:
        editable_goal(conn, ctx, goal_id)
        conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
    return {"ok": True}


# ---------------------------------------------------------------- transactions

@app.get("/api/transactions")
def transactions(request: Request, limit: int = 200, category: Optional[str] = None, member_id: Optional[int] = None,
                 q: Optional[str] = None):
    ctx = ctx_of(request)
    sql, params = "SELECT * FROM transactions WHERE room_id = ?", [ctx["member"]["room_id"]]
    if category:
        sql += " AND category = ?"
        params.append(category)
    if member_id:
        sql += " AND member_id = ?"
        params.append(member_id)
    if q:
        sql += " AND description LIKE ?"
        params.append(f"%{q}%")
    sql += " ORDER BY date DESC, id DESC LIMIT ?"
    params.append(min(limit, 1000))
    with db.session() as conn:
        rows = db.rows(conn, sql, params)
        members = {m["id"]: m["display_name"] for m in room_members(conn, ctx["member"]["room_id"])}
    for r in rows:
        r["member"] = members.get(r["member_id"])
    return {"transactions": rows, "categories": CATEGORY_NAMES, "members": members}


class CategoryFix(BaseModel):
    category: str


def apply_correction(conn, rid: int, text: str, category: str, exclude_id: str = None) -> int:
    """Remember a category for this merchant and re-label every model-labelled transaction from it."""
    key = ml_service.merchant_key(text)
    conn.execute("INSERT OR REPLACE INTO corrections(room_id, merchant_key, category, example, created_at) "
                 "VALUES (?, ?, ?, ?, ?)", (rid, key, category, text, datetime.now().isoformat()))
    updated = 0
    for r in db.rows(conn, "SELECT id, amount, description FROM transactions WHERE room_id = ? "
                           "AND category_source = 'model' AND id != ?", (rid, exclude_id or "")):
        if ml_service.merchant_key(ml_service.with_sign(r["amount"], r["description"])) == key:
            conn.execute("UPDATE transactions SET category = ? WHERE id = ?", (category, r["id"]))
            updated += 1
    return updated


@app.post("/api/transactions/{tx_id}/category")
def fix_category(tx_id: str, body: CategoryFix, request: Request):
    """Correct a category: applies to every transaction from this merchant, then retrains in the background."""
    ctx = ctx_of(request)
    rid = ctx["member"]["room_id"]
    if body.category not in CATEGORY_NAMES:
        raise HTTPException(400, f"Unknown category {body.category}")
    with db.session() as conn:
        tx = db.one(conn, "SELECT * FROM transactions WHERE id = ? AND room_id = ?", (tx_id, rid))
        if not tx:
            raise HTTPException(404, "Transaction not found")
        updated = apply_correction(conn, rid, ml_service.with_sign(tx["amount"], tx["description"]), body.category, tx_id)
        conn.execute("UPDATE transactions SET category = ?, category_source = 'user' WHERE id = ?", (body.category, tx_id))
        fixes = db.rows(conn, "SELECT example, category FROM corrections WHERE room_id = ?", (rid,))
    categorizer.retrain_async(fixes)
    return {"updated_same_merchant": updated, "retraining": True}


# ---------------------------------------------------------------- uploads (Gemini)

@app.post("/api/uploads")
async def upload(request: Request, file: UploadFile = File(...)):
    ctx = ctx_of(request)
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File is larger than 15 MB.")
    today = str(ml_service.now().date())
    try:
        result = gemini.extract_transactions(file.filename or "upload", content, file.content_type or "", today)
    except gemini.GeminiError as e:
        raise HTTPException(400, str(e))
    if not result["rows"]:
        raise HTTPException(422, "Gemini found no expenses in this file.")
    with db.session() as conn:
        texts = [ml_service.with_sign(r["amount"], r["description"]) for r in result["rows"]]
        cats = categorizer.predict(texts, corrections_map(conn, ctx["member"]["room_id"]))
        for r, c in zip(result["rows"], cats):
            item_cat = ml_service.category_for_product(" ".join(r["items"]), "") if r["items"] else None
            r["category"] = item_cat if (item_cat and item_cat != "shopping" and c == "shopping") else c
        cur = conn.execute("INSERT INTO uploads(room_id, member_id, filename, kind, rows_json, created_at) "
                           "VALUES (?, ?, ?, ?, ?, ?)",
                           (ctx["member"]["room_id"], ctx["member"]["id"], file.filename or "upload",
                            result["document_type"], json.dumps(result["rows"]), datetime.now().isoformat()))
    return {"upload_id": cur.lastrowid, "document_type": result["document_type"], "rows": result["rows"],
            "categories": CATEGORY_NAMES}


class ConfirmIn(BaseModel):
    rows: List[dict]


@app.post("/api/uploads/{upload_id}/confirm")
def confirm_upload(upload_id: int, body: ConfirmIn, request: Request):
    ctx = ctx_of(request)
    with db.session() as conn:
        up = db.one(conn, "SELECT * FROM uploads WHERE id = ? AND room_id = ? AND member_id = ?",
                    (upload_id, ctx["member"]["room_id"], ctx["member"]["id"]))
        if not up or up["status"] != "preview":
            raise HTTPException(404, "Upload not found or already imported.")
        items = []
        for i, r in enumerate(body.rows):
            try:
                items.append({"id": f"up-{upload_id}-{i}", "date": str(pd.Timestamp(r["date"]).date()),
                              "amount": float(r["amount"]), "description": str(r["description"])[:120],
                              "channel": "upload",
                              "category": r.get("category") if r.get("category") in CATEGORY_NAMES else None})
            except (KeyError, ValueError, TypeError):
                raise HTTPException(400, f"Row {i + 1} is not valid.")
        n = insert_transactions(conn, ctx["member"]["room_id"], ctx["member"]["id"], items, "upload")
        conn.execute("UPDATE uploads SET status = 'imported' WHERE id = ?", (upload_id,))
    return {"imported": n}


# ---------------------------------------------------------------- PayPal

@app.post("/api/paypal/sync")
def paypal_sync(request: Request):
    ctx = ctx_of(request)
    try:
        items = paypal.fetch_transactions()
    except paypal.PayPalError as e:
        raise HTTPException(400, str(e))
    with db.session() as conn:
        members = room_members(conn, ctx["member"]["room_id"])
        by_email = {m["paypal_email"]: m["id"] for m in members if m["paypal_email"]}
        names = {m["id"]: m["display_name"] for m in members}
        for t in items:
            t["member_id"] = by_email.get(t["payer_email"]) or by_email.get(t["payee_email"]) or ctx["member"]["id"]
        n = insert_transactions(conn, ctx["member"]["room_id"], ctx["member"]["id"], items, "paypal")
    owners = {}
    for t in items:
        owners[names.get(t["member_id"], "?")] = owners.get(names.get(t["member_id"], "?"), 0) + 1
    return {"imported": n, "by_member": owners}


# ---------------------------------------------------------------- purchase verdict (extension and website)

class PurchaseIn(BaseModel):
    title: str = ""
    price: float = Field(gt=0)
    url: str = ""
    category: Optional[str] = None


def verdict_for(ctx: dict, p: PurchaseIn) -> dict:
    today = ml_service.now()
    with db.session() as conn:
        room = load_room(conn, ctx["member"]["room_id"])
        cached = db.one(conn, "SELECT gemini_price FROM price_cache WHERE title = ?", (p.title[:200],)) if p.title else None
    require_data(room)
    category = p.category if p.category in CATEGORY_NAMES else ml_service.category_for_product(p.title, p.url)
    kind = room["kinds"].get(category, ml_service.default_kind(category))
    is_need = kind == "need"
    name = CATEGORY_NAMES.get(category, category)

    market = None
    # Market prices come from Amazon products: meaningful for goods, not for tickets, trips, meals or subscriptions.
    if p.title.strip() and category in MARKET_CATEGORIES:
        market = prices.estimate(p.title, category, cached_gemini=cached["gemini_price"] if cached else None)
        if market["gemini"] and not cached:
            with db.session() as conn:
                conn.execute("INSERT OR REPLACE INTO price_cache(title, gemini_price, created_at) VALUES (?, ?, ?)",
                             (p.title[:200], market["gemini"], datetime.now().isoformat()))

    df = room["df"]
    state = family_state(room, today)
    limit = room["limits"].get(category)
    risk_cat = category if category in ml_service.FORECAST_CATEGORIES else None
    before = ml_service.features_with_budget(state, risk_cat, today, 0.0, limit) if risk_cat else None
    after = ml_service.features_with_budget(state, risk_cat, today, p.price, limit) if risk_cat else None
    r0 = overspend.probability(before) if before is not None else None
    r1 = overspend.probability(after) if after is not None else None

    free = finance.monthly_free_cash(df, today)
    plans = finance.plan_goals([g for g in room["goals"] if g["member_id"] is None], free, today)
    behind = [g for g in plans if not g["on_track"]]
    goal = behind[0] if behind else None
    delay = int(round(p.price / (free / finance.AVG_DAYS_IN_MONTH))) if goal and free > 0 else None

    v = decide(Signals(price=p.price, category_name=name, is_need=is_need, risk_before=r0, risk_after=r1,
                       warn_threshold=overspend.threshold, usual_p90=finance.usual_p90(df, category, today),
                       market_low=market["low"] if market else None, market_high=market["high"] if market else None,
                       goal_name=goal["name"] if goal else None, goal_behind=bool(goal) and not is_need,
                       goal_delay_days=delay))

    reasonable = None
    if risk_cat and not is_need:
        def risk_at(x):
            return overspend.probability(ml_service.features_with_budget(state, risk_cat, today, x, limit))
        reasonable = reasonable_price(risk_at, overspend.threshold, upper=max(p.price * 3, 50.0))
    budget = float(before["budget"]) if before is not None else None
    spent = float(before["spent_to_date"]) if before is not None else None
    titles = {"buy": "Buy", "think": "Think about it", "not_worth_it": "Not worth it"}
    return {
        "decision": v.decision, "title_text": titles[v.decision], "reasons": v.reasons, "checks": v.checks,
        "category": category, "category_name": name, "kind": kind,
        "risk_before": None if r0 is None else round(r0, 3), "risk_after": None if r1 is None else round(r1, 3),
        "spent_this_month": None if spent is None else round(spent, 2),
        "budget": None if budget is None else round(budget, 2),
        "market": market, "reasonable_price": None if reasonable is None else round(reasonable, 2),
        "no_room_this_month": bool(risk_cat and not is_need and reasonable is None),
        "next_month_starts": str((today.to_period("M") + 1).to_timestamp().date()),
        "goal": goal["name"] if goal else None, "goal_delay_days": delay,
        "checked_for": ctx["member"]["display_name"], "uses": "family budget",
        "title": p.title, "price": p.price, "disclaimer": DISCLAIMER,
    }


@app.post("/api/check-purchase")
def check_purchase(p: PurchaseIn, request: Request):
    return verdict_for(ctx_of(request), p)


class PostponeIn(PurchaseIn):
    decision: Optional[str] = None
    probability: Optional[float] = None


@app.post("/api/postpone")
def postpone(p: PostponeIn, request: Request):
    ctx = ctx_of(request)
    remind = str((ml_service.now().to_period("M") + 1).to_timestamp().date())
    category = p.category or ml_service.category_for_product(p.title, p.url)
    with db.session() as conn:
        cur = conn.execute("INSERT INTO postponed(room_id, member_id, title, price, url, category, decision, probability, "
                           "created_at, remind_on) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (ctx["member"]["room_id"], ctx["member"]["id"], p.title or "Item", p.price, p.url, category,
                            p.decision, p.probability, datetime.now().isoformat(timespec="seconds"), remind))
    return {"id": cur.lastrowid, "remind_on": remind}


@app.get("/api/postponed")
def postponed_list(request: Request):
    ctx = ctx_of(request)
    with db.session() as conn:
        items = db.rows(conn, "SELECT * FROM postponed WHERE room_id = ? ORDER BY created_at DESC",
                        (ctx["member"]["room_id"],))
        names = {m["id"]: m["display_name"] for m in room_members(conn, ctx["member"]["room_id"])}
    for i in items:
        i["member"] = names.get(i["member_id"])
    return {"items": items,
            "waiting_total": round(sum(i["price"] for i in items if i["status"] == "waiting"), 2),
            "not_bought_total": round(sum(i["price"] for i in items if i["status"] == "dropped"), 2)}


class StatusIn(BaseModel):
    status: str


@app.patch("/api/postponed/{item_id}")
def postponed_status(item_id: int, body: StatusIn, request: Request):
    ctx = ctx_of(request)
    if body.status not in ("waiting", "bought", "dropped"):
        raise HTTPException(400, "Status must be waiting, bought or dropped")
    with db.session() as conn:
        conn.execute("UPDATE postponed SET status = ? WHERE id = ? AND room_id = ?",
                     (body.status, item_id, ctx["member"]["room_id"]))
    return {"ok": True}


# ---------------------------------------------------------------- assistant

class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    context: Optional[dict] = None


@app.post("/api/chat")
def chat(body: ChatIn, request: Request):
    ctx = ctx_of(request)
    today = ml_service.now()
    with db.session() as conn:
        room = load_room(conn, ctx["member"]["room_id"])
        plans = future_plans(conn, ctx["member"]["room_id"], today)
        postponed = db.rows(conn, "SELECT * FROM postponed WHERE room_id = ? ORDER BY created_at DESC",
                            (ctx["member"]["room_id"],))
    if room["df"].empty:
        return {"reply": "Connect PayPal, upload a statement or load the demo family first.", "intent": "help"}
    data = {"room": room, "state": family_state(room, today), "overspend": overspend, "today": today,
            "member": ctx["member"], "postponed": postponed,
            "upcoming": lambda: upcoming_list(room, plans, today),
            "verdict": lambda title, price, url="", category=None: verdict_for(
                ctx, PurchaseIn(title=title, price=price, url=url, category=category))}
    out = assistant_mod.answer(assistant, body.message, data, body.context)
    out["disclaimer"] = DISCLAIMER
    return out


# ---------------------------------------------------------------- website

app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")
