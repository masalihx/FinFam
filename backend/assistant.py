"""The FinPilot assistant: one brain for the website chat and the extension.

1. An ML intent classifier (ml/train_intent.py) decides what the question is about.
2. Code pulls the details out of the text: category, month, amount.
3. Code computes every number from the family's data; templates turn them into words.
No language model writes numbers, so the assistant cannot invent them.
"""
import re

import joblib
import pandas as pd

from backend import finance, ml_service
from backend.config import MODELS_DIR
from backend.finance import CATEGORY_NAMES

MIN_CONFIDENCE = 0.35

CATEGORY_WORDS = {
    "dining": ["dining", "restaurant", "eating out", "eat out", "coffee", "cafe", "takeout", "delivery", "fast food", "lunch", "dinner"],
    "groceries": ["grocer", "supermarket", "food shopping"],
    "shopping": ["shopping", "clothes", "clothing", "amazon", "online", "stuff"],
    "transportation": ["transport", "gas", "fuel", "uber", "lyft", "car", "taxi", "transit", "metro"],
    "entertainment": ["entertainment", "movie", "cinema", "games", "concert", "fun"],
    "subscriptions": ["subscription", "netflix", "spotify", "streaming", "prime"],
    "travel": ["travel", "vacation", "flight", "hotel", "trip"],
    "health": ["health", "pharmacy", "doctor", "medicine", "dentist"],
    "personal_care": ["personal care", "haircut", "salon", "barber", "gym", "beauty"],
    "housing": ["rent", "mortgage", "housing"],
    "utilities": ["bills", "utilities", "electric", "internet", "phone bill", "water"],
    "insurance": ["insurance"],
}
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december"]


class Assistant:
    def __init__(self):
        self.model = joblib.load(MODELS_DIR / "intent.joblib")

    def intent(self, text: str):
        proba = self.model.predict_proba([text])[0]
        i = proba.argmax()
        return self.model.classes_[i], float(proba[i])


# ---------- slot extraction ----------

def find_category(text: str):
    low = text.lower()
    for cat, words in CATEGORY_WORDS.items():
        if any(w in low for w in words):
            return cat
    return None


def find_amount(text: str):
    m = re.search(r"\$\s?(\d[\d,]*(?:\.\d+)?)|(\d[\d,]*(?:\.\d+)?)\s?(?:dollars|bucks|usd)", text.lower())
    if not m:
        return None
    return float((m.group(1) or m.group(2)).replace(",", ""))


def find_month(text: str, today: pd.Timestamp) -> pd.Period:
    low = text.lower()
    cur = today.to_period("M")
    if "last month" in low:
        return cur - 1
    for i, name in enumerate(MONTHS, start=1):
        # "may" is also a verb ("may I buy..."), so only "in may" counts.
        pattern = r"\bin may\b" if name == "may" else r"\b(" + name + "|" + name[:3] + r")\b"
        if re.search(pattern, low):
            p = pd.Period(year=today.year, month=i, freq="M")
            return p if p <= cur else p - 12
    return cur


def find_item(text: str) -> str:
    m = re.search(r"(?:buy|get|afford|purchase|order|spend .* on)\s+(?:a |an |the |new |some )*([a-z0-9 \-']{2,40}?)(?:\s+for\b|\?|$|,)",
                  text.lower())
    return m.group(1).strip() if m else ""


# ---------- answers ----------

def answer(assistant: Assistant, text: str, data: dict, context: dict = None) -> dict:
    """data: df, state, overspend, overrides, goals, postponed, categorizer, today."""
    intent, conf = assistant.intent(text)
    if conf < MIN_CONFIDENCE:
        intent = "help"
    ctx = context or {}
    # Asked from the extension about waiting ("what if I wait until payday?").
    if ctx.get("price") and WAIT_RE.search(text) and intent in ("help", "can_afford", "budget_left", "spending"):
        intent = "wait"
    reply = HANDLERS[intent](text, data, ctx)
    return {"reply": reply, "intent": intent, "confidence": round(conf, 3)}


def _spending(text, d, ctx):
    df, today = d["df"], d["today"]
    cat = find_category(text)
    month = find_month(text, today)
    rows = finance.spending(df[df["month"] == month])
    label = "this month" if month == today.to_period("M") else "in " + month.strftime("%B %Y")
    if cat:
        total = -rows.loc[rows["category"] == cat, "amount"].sum()
        n = int((rows["category"] == cat).sum())
        prev = finance.spending(df[df["month"] == month - 1])
        prev_total = -prev.loc[prev["category"] == cat, "amount"].sum()
        change = ""
        if prev_total > 0:
            diff = (total - prev_total) / prev_total
            change = f" That is {abs(diff):.0%} {'more' if diff > 0 else 'less'} than the month before ({finance_money(prev_total)})."
        return f"You spent {finance_money(total)} on {CATEGORY_NAMES[cat]} {label} ({n} transactions).{change}"
    by_cat = (-rows.groupby("category")["amount"].sum()).sort_values(ascending=False)
    top = ", ".join(f"{CATEGORY_NAMES.get(c, c)} {finance_money(v)}" for c, v in by_cat.head(4).items() if v > 0)
    return f"You spent {finance_money(by_cat.sum())} {label}. Biggest: {top}."


def _can_afford(text, d, ctx):
    price = find_amount(text) or ctx.get("price")
    if not price:
        return "How much does it cost? For example: “Can I buy a jacket for $120?”"
    item = find_item(text) or ctx.get("title") or "this"
    cat = find_category(text) or ctx.get("category") or \
        ml_service.category_for_product(d["categorizer"], item, ctx.get("url", ""))
    if cat not in ml_service.FORECAST_CATEGORIES:
        cat = "shopping"
    free = finance.monthly_free_cash(d["df"], d["today"])
    plans = {p["id"]: p for p in finance.plan_goals(d["goals"], free, d["today"])}
    goals = sorted(d["goals"], key=lambda g: (plans[g["id"]]["on_track"], g["deadline"]))
    r = finance.check_purchase(d["state"], d["overspend"], cat, float(price), d["today"],
                               d["overrides"].get(cat), goals, free)
    head = {"red": "🔴 Better to wait.", "yellow": "🟡 Think it over.", "green": "🟢 Looks fine."}[r["light"]]
    return f"{head} {r['reason']}"


def _budget_left(text, d, ctx):
    cat = find_category(text)
    summary = finance.month_summary(d["df"], d["state"], d["overspend"], d["today"], d["overrides"])
    cats = {c["category"]: c for c in summary["categories"]}
    if cat and cat in cats and cats[cat]["budget"] is not None:
        c = cats[cat]
        left = c["budget"] - c["spent"]
        lead = (f"{finance_money(left)} left of your usual {finance_money(c['budget'])} for {c['name']}"
                if left >= 0 else f"Already {finance_money(-left)} over your usual {finance_money(c['budget'])} for {c['name']}")
        return (f"{lead}, with {summary['days_left']} days to go. "
                f"Chance of ending the month over: {c['overspend_probability']:.0%}.")
    risky = [c for c in summary["categories"] if c["overspend_probability"] is not None]
    risky.sort(key=lambda c: -c["overspend_probability"])
    lines = [f"• {c['name']}: {finance_money(c['spent'])} of {finance_money(c['budget'])}, risk {c['overspend_probability']:.0%}"
             for c in risky[:4]]
    return f"{summary['days_left']} days left this month. Highest overspending risk:\n" + "\n".join(lines)


def _goals(text, d, ctx):
    free = finance.monthly_free_cash(d["df"], d["today"])
    plans = finance.plan_goals(d["goals"], free, d["today"])
    if not plans:
        return "You have no goals yet. Add one on the Goals tab, for example a college fund or a car."
    lines = []
    for p in plans:
        status = "on track ✅" if p["on_track"] else "behind ⚠️"
        lines.append(f"• {p['name']}: {finance_money(p['saved'])} of {finance_money(p['target'])}, needs "
                     f"{finance_money(p['needed_per_month'])}/month, reached {p['projected_date']} ({status}).")
    tail = f"\nYou keep about {finance_money(free)} a month after spending."
    behind = [p for p in plans if not p["on_track"]]
    if behind:
        gap = sum(p["needed_per_month"] - p["allocated_per_month"] for p in behind)
        tail += f" To get every goal on track you need about {finance_money(gap)} more per month."
    return "\n".join(lines) + tail


def _where_losing(text, d, ctx):
    df, today = d["df"], d["today"]
    cur = today.to_period("M")
    last_full = cur - 1
    spend = finance.spending(df)
    monthly = (-spend.groupby(["month", "category"])["amount"].sum()).unstack(fill_value=0.0)
    hist = monthly.loc[(monthly.index < last_full) & (monthly.index >= last_full - 6)]
    if last_full not in monthly.index or hist.empty:
        return "I need a few months of history to see where money goes."
    usual = hist.median()
    diff = (monthly.loc[last_full] - usual).sort_values(ascending=False)
    lines = [f"• {CATEGORY_NAMES.get(c, c)}: {finance_money(monthly.loc[last_full, c])} vs usual {finance_money(usual[c])} (+{finance_money(v)})"
             for c, v in diff.items() if v > 20][:3]
    wants = [c for c in ("dining", "shopping", "entertainment", "subscriptions", "travel", "personal_care") if c in monthly.columns]
    income = df[(df["month"] == last_full) & (df["category"] == "income")]["amount"].sum()
    wants_total = monthly.loc[last_full, wants].sum()
    out = [f"In {last_full.strftime('%B')}, these grew the most compared with your usual month:"] + (lines or ["• nothing unusual"])
    if income > 0:
        out.append(f"“Wants” (dining, shopping, fun, subscriptions) took {wants_total / income:.0%} of income; a common guide is 30%.")
    subs = monthly.loc[last_full].get("subscriptions", 0.0)
    if subs > 0:
        out.append(f"Subscriptions: {finance_money(subs)} a month, {finance_money(subs * 12)} a year. Worth checking which ones you still use.")
    return "\n".join(out)


def _postponed(text, d, ctx):
    items = d["postponed"]
    waiting = [i for i in items if i["status"] == "waiting"]
    dropped = [i for i in items if i["status"] == "dropped"]
    if not items:
        return "Nothing postponed yet. When the extension says “better wait”, press Postpone."
    lines = [f"• {i['title'][:50]}: {finance_money(i['price'])}, reminder {i['remind_on']}" for i in waiting[:5]]
    out = [f"{len(waiting)} purchase(s) waiting, {finance_money(sum(i['price'] for i in waiting))} not spent yet."] + lines
    if dropped:
        out.append(f"You decided not to buy {len(dropped)} item(s) and kept {finance_money(sum(i['price'] for i in dropped))}.")
    return "\n".join(out)


WAIT_RE = re.compile(r"\b(wait|payday|next month|later|postpone|tomorrow)\b", re.I)


def _wait(text, d, ctx):
    """What happens if the purchase moves to next month."""
    price = float(ctx["price"])
    cat = ctx.get("category") if ctx.get("category") in ml_service.FORECAST_CATEGORIES else "shopping"
    row = ml_service.features_with_budget(d["state"], cat, d["today"], 0.0, d["overrides"].get(cat))
    next_start = finance.next_month_start(d["today"])
    income_days = d["df"][(d["df"]["category"] == "income") & (d["df"]["amount"] > 500)]["date"].dt.day
    payday = f" Your pay usually arrives around day {int(income_days.median())} of the month." if len(income_days) else ""
    if row is None:
        return f"If you wait until {next_start}, it goes into next month's spending.{payday}"
    budget = float(row["budget"])
    share = price / budget if budget > 0 else 0
    now_p = d["overspend"].probability(ml_service.features_with_budget(d["state"], cat, d["today"], price, d["overrides"].get(cat)))
    return (f"Buying now: {now_p:.0%} chance of going over your {CATEGORY_NAMES[cat]} budget this month. "
            f"Waiting until {next_start}: it starts a fresh month and uses {share:.0%} of your usual "
            f"{finance_money(budget)} for {CATEGORY_NAMES[cat]}.{payday} Press Postpone and I'll remind you.")


def _help(text, d, ctx):
    return ("I can answer questions about your family's money, using your own data:\n"
            "• “How much did we spend on dining last month?”\n"
            "• “Can I buy a $200 jacket?”\n"
            "• “How much is left for shopping?”\n"
            "• “How are our goals?”\n"
            "• “Where are we losing money?”\n"
            "• “What did I postpone?”")


def finance_money(x: float) -> str:
    return ("−$" if x < 0 else "$") + f"{abs(x):,.0f}"


HANDLERS = {"spending": _spending, "can_afford": _can_afford, "budget_left": _budget_left, "goals": _goals,
            "where_losing": _where_losing, "postponed": _postponed, "help": _help, "wait": _wait}
