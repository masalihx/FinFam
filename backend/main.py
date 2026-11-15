"""FinPilot API and website.

Run from the project root:
    .venv/bin/uvicorn backend.main:app --reload --port 8000
Then open http://localhost:8000
"""
from datetime import datetime
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend import assistant as assistant_mod
from backend import db, demo, finance, ml_service, paypal
from backend.config import WEB_DIR
from backend.finance import CATEGORY_NAMES

DISCLAIMER = "This project is a prototype and is not financial advice."

app = FastAPI(title="FinPilot", description=DISCLAIMER)
# The Chrome extension calls the API from shop pages; everything runs on the family's own computer.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

categorizer = ml_service.Categorizer()
overspend = ml_service.OverspendModel()
assistant = assistant_mod.Assistant()
db.init()


# ---------- helpers ----------

def load_all(conn):
    df = finance.tx_frame(db.rows(conn, "SELECT * FROM transactions ORDER BY date"))
    profile = db.get_profile(conn)
    overrides = {r["category"]: r["amount"] for r in db.rows(conn, "SELECT * FROM budgets")}
    goals = db.rows(conn, "SELECT * FROM goals ORDER BY deadline")
    return df, profile, overrides, goals


def require_data(df):
    if df.empty:
        raise HTTPException(409, "No transactions yet. Connect PayPal or load the demo family first.")


def state_for(df, profile):
    return ml_service.family_state(df, float(profile.get("household_income") or 0),
                                   float(profile.get("children") or 0))


def corrections_map(conn) -> dict:
    return {r["merchant_key"]: r["category"] for r in db.rows(conn, "SELECT * FROM corrections")}


def insert_transactions(conn, items: list, source: str) -> int:
    texts = [("[debit] " if t["amount"] < 0 else "[credit] ") + t["description"] for t in items]
    cats = categorizer.predict(texts, corrections_map(conn))
    conn.executemany(
        "INSERT OR REPLACE INTO transactions(id, date, amount, description, merchant, channel, category, "
        "category_source, source) VALUES (?, ?, ?, ?, ?, ?, ?, 'model', ?)",
        [(t["id"], t["date"], t["amount"], t["description"], t.get("merchant"), t.get("channel"), c, source)
         for t, c in zip(items, cats)])
    return len(items)


# ---------- data sources ----------

@app.get("/api/status")
def status():
    with db.session() as conn:
        n = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        profile = db.get_profile(conn)
    return {"transactions": n, "profile": profile, "paypal_configured": paypal.configured(),
            "categorizer_retraining": categorizer.retraining, "disclaimer": DISCLAIMER}


@app.post("/api/import/demo")
def import_demo():
    today = ml_service.now()
    items = demo.demo_transactions(today)
    with db.session() as conn:
        conn.execute("DELETE FROM transactions WHERE source = 'demo'")
        n = insert_transactions(conn, items, "demo")
        db.set_profile(conn, **demo.demo_profile())
        if conn.execute("SELECT COUNT(*) FROM goals").fetchone()[0] == 0:
            for g in demo.DEMO_GOALS:
                conn.execute("INSERT INTO goals(name, target, saved, deadline, created_at) VALUES (?, ?, ?, ?, ?)",
                             (g["name"], g["target"], g["saved"], g["deadline"], datetime.now().isoformat()))
    return {"imported": n, "source": "demo"}


@app.post("/api/import/paypal")
def import_paypal():
    try:
        items = paypal.fetch_transactions()
    except paypal.PayPalError as e:
        raise HTTPException(400, str(e))
    with db.session() as conn:
        n = insert_transactions(conn, items, "paypal")
        db.set_profile(conn, paypal_connected="yes", paypal_last_sync=datetime.now().isoformat(timespec="seconds"))
    return {"imported": n, "source": "paypal"}


# ---------- dashboard ----------

@app.get("/api/summary")
def summary():
    with db.session() as conn:
        df, profile, overrides, goals = load_all(conn)
    require_data(df)
    today = ml_service.now()
    state = state_for(df, profile)
    out = finance.month_summary(df, state, overspend, today, overrides)
    out["goals"] = finance.plan_goals(goals, out["free_cash_per_month"], today)
    out["disclaimer"] = DISCLAIMER
    return out


@app.get("/api/transactions")
def transactions(limit: int = 100, category: Optional[str] = None):
    sql, params = "SELECT * FROM transactions", []
    if category:
        sql += " WHERE category = ?"
        params.append(category)
    sql += " ORDER BY date DESC, id DESC LIMIT ?"
    params.append(limit)
    with db.session() as conn:
        return {"transactions": db.rows(conn, sql, params), "categories": CATEGORY_NAMES}


class CategoryFix(BaseModel):
    category: str


@app.post("/api/transactions/{tx_id}/category")
def fix_category(tx_id: str, body: CategoryFix):
    """The family corrects a category: applies to every transaction from this merchant and retrains."""
    if body.category not in CATEGORY_NAMES:
        raise HTTPException(400, f"Unknown category {body.category}")
    with db.session() as conn:
        tx = conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
        if tx is None:
            raise HTTPException(404, "Transaction not found")
        text = ("[debit] " if tx["amount"] < 0 else "[credit] ") + tx["description"]
        key = ml_service.merchant_key(text)
        conn.execute("INSERT OR REPLACE INTO corrections(merchant_key, category, example, created_at) "
                     "VALUES (?, ?, ?, ?)", (key, body.category, text, datetime.now().isoformat()))
        # Same merchant pattern -> same category, right away.
        updated = 0
        for r in db.rows(conn, "SELECT id, amount, description FROM transactions WHERE category_source = 'model'"):
            t = ("[debit] " if r["amount"] < 0 else "[credit] ") + r["description"]
            if ml_service.merchant_key(t) == key:
                conn.execute("UPDATE transactions SET category = ?, category_source = 'model' WHERE id = ?",
                             (body.category, r["id"]))
                updated += 1
        conn.execute("UPDATE transactions SET category = ?, category_source = 'user' WHERE id = ?",
                     (body.category, tx_id))
        fixes = db.rows(conn, "SELECT example, category FROM corrections")
    categorizer.retrain_async(fixes)
    return {"updated_same_merchant": updated, "retraining": True}


# ---------- budgets and goals ----------

class BudgetIn(BaseModel):
    amount: Optional[float] = Field(None, ge=0)  # None removes the override


@app.put("/api/budgets/{category}")
def set_budget(category: str, body: BudgetIn):
    if category not in ml_service.FORECAST_CATEGORIES:
        raise HTTPException(400, f"Budgets are available for: {ml_service.FORECAST_CATEGORIES}")
    with db.session() as conn:
        if body.amount is None:
            conn.execute("DELETE FROM budgets WHERE category = ?", (category,))
        else:
            conn.execute("INSERT OR REPLACE INTO budgets(category, amount) VALUES (?, ?)", (category, body.amount))
    return {"category": category, "amount": body.amount}


class GoalIn(BaseModel):
    name: str
    target: float = Field(gt=0)
    saved: float = Field(0, ge=0)
    deadline: str  # YYYY-MM-DD


@app.get("/api/goals")
def list_goals():
    with db.session() as conn:
        df, _, _, goals = load_all(conn)
    today = ml_service.now()
    free = finance.monthly_free_cash(df, today) if not df.empty else 0.0
    return {"goals": finance.plan_goals(goals, free, today), "free_cash_per_month": free}


@app.post("/api/goals")
def add_goal(goal: GoalIn):
    try:
        pd.Timestamp(goal.deadline)
    except ValueError:
        raise HTTPException(400, "deadline must be a date like 2030-09-01")
    with db.session() as conn:
        cur = conn.execute("INSERT INTO goals(name, target, saved, deadline, created_at) VALUES (?, ?, ?, ?, ?)",
                           (goal.name, goal.target, goal.saved, goal.deadline, datetime.now().isoformat()))
    return {"id": cur.lastrowid}


@app.put("/api/goals/{goal_id}")
def update_goal(goal_id: int, goal: GoalIn):
    with db.session() as conn:
        conn.execute("UPDATE goals SET name = ?, target = ?, saved = ?, deadline = ? WHERE id = ?",
                     (goal.name, goal.target, goal.saved, goal.deadline, goal_id))
    return {"id": goal_id}


@app.delete("/api/goals/{goal_id}")
def delete_goal(goal_id: int):
    with db.session() as conn:
        conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
    return {"deleted": goal_id}


# ---------- extension: purchase check and postponed list ----------

class PurchaseIn(BaseModel):
    title: str = ""
    price: float = Field(gt=0)
    url: str = ""
    category: Optional[str] = None


@app.post("/api/check-purchase")
def check(p: PurchaseIn):
    with db.session() as conn:
        df, profile, overrides, goals = load_all(conn)
    require_data(df)
    today = ml_service.now()
    category = p.category if p.category in ml_service.FORECAST_CATEGORIES else \
        ml_service.category_for_product(categorizer, p.title, p.url)
    state = state_for(df, profile)
    free = finance.monthly_free_cash(df, today)
    plans = {pl["id"]: pl for pl in finance.plan_goals(goals, free, today)}
    # Talk about the goal that is behind schedule first; otherwise the nearest deadline.
    goals = sorted(goals, key=lambda g: (plans[g["id"]]["on_track"], g["deadline"]))
    result = finance.check_purchase(state, overspend, category, p.price, today,
                                    overrides.get(category), goals, free)
    result.update({"title": p.title, "price": p.price, "disclaimer": DISCLAIMER})
    return result


class PostponeIn(PurchaseIn):
    probability: Optional[float] = None


@app.post("/api/postpone")
def postpone(p: PostponeIn):
    today = ml_service.now()
    category = p.category or ml_service.category_for_product(categorizer, p.title, p.url)
    with db.session() as conn:
        cur = conn.execute(
            "INSERT INTO postponed(title, price, url, category, probability, created_at, remind_on) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (p.title, p.price, p.url, category, p.probability, datetime.now().isoformat(timespec="seconds"),
             finance.next_month_start(today)))
    return {"id": cur.lastrowid, "remind_on": finance.next_month_start(today)}


@app.get("/api/postponed")
def postponed_list():
    with db.session() as conn:
        items = db.rows(conn, "SELECT * FROM postponed ORDER BY created_at DESC")
    waiting = [i for i in items if i["status"] == "waiting"]
    dropped = [i for i in items if i["status"] == "dropped"]
    return {"items": items, "waiting_total": round(sum(i["price"] for i in waiting), 2),
            "not_bought_total": round(sum(i["price"] for i in dropped), 2)}


class PostponedStatus(BaseModel):
    status: str


@app.patch("/api/postponed/{item_id}")
def postponed_status(item_id: int, body: PostponedStatus):
    if body.status not in ("waiting", "bought", "dropped"):
        raise HTTPException(400, "status must be waiting, bought or dropped")
    with db.session() as conn:
        conn.execute("UPDATE postponed SET status = ? WHERE id = ?", (body.status, item_id))
    return {"id": item_id, "status": body.status}


# ---------- assistant ----------

class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    context: Optional[dict] = None  # product the extension is looking at


@app.post("/api/chat")
def chat(body: ChatIn):
    with db.session() as conn:
        df, profile, overrides, goals = load_all(conn)
        postponed = db.rows(conn, "SELECT * FROM postponed ORDER BY created_at DESC")
    if df.empty:
        return {"reply": "Connect PayPal or load the demo family first, then ask me anything about your money.",
                "intent": "help", "confidence": 1.0}
    data = {"df": df, "state": state_for(df, profile), "overspend": overspend, "overrides": overrides,
            "goals": goals, "postponed": postponed, "categorizer": categorizer, "today": ml_service.now()}
    out = assistant_mod.answer(assistant, body.message, data, body.context)
    out["disclaimer"] = DISCLAIMER
    return out


# ---------- website ----------

if (WEB_DIR / "index.html").exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/")
def index():
    page = WEB_DIR / "index.html"
    if not page.exists():
        return {"message": "FinPilot API is running. The website is not built yet.", "docs": "/docs"}
    return FileResponse(page)
