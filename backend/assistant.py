"""The FinPilot assistant: one brain for the website chat and the extension.

1. An ML intent classifier (ml/train_intent.py) decides what the question is about.
2. Code pulls the details out of the text: category, month, amount, "my" vs family.
3. Code computes every number from the room's data; templates turn them into words.
No language model writes the numbers, so the assistant cannot invent them.
"""
import re

import joblib
import pandas as pd

from backend import finance, ml_service
from backend.config import MODELS_DIR
from backend.finance import CATEGORY_NAMES, money

MIN_CONFIDENCE = 0.35
CATEGORY_WORDS = {
    "dining": ["dining", "restaurant", "eating out", "eat out", "coffee", "cafe", "takeout", "delivery", "fast food",
               "lunch", "dinner"],
    "groceries": ["grocer", "supermarket", "food shopping"],
    "shopping": ["shopping", "clothes", "clothing", "amazon", "online", "jacket", "shoes", "sneakers", "headphones"],
    "transportation": ["transport", "gas", "fuel", "uber", "lyft", "taxi", "transit", "metro"],
    "entertainment": ["entertainment", "movie", "cinema", "games", "concert", "ticket", "fun"],
    "subscriptions": ["subscription", "netflix", "spotify", "streaming", "prime"],
    "travel": ["travel", "vacation", "flight", "hotel", "trip"],
    "health": ["health", "pharmacy", "doctor", "medicine", "dentist"],
    "personal_care": ["personal care", "haircut", "salon", "barber", "gym", "beauty", "makeup"],
    "housing": ["rent", "mortgage", "housing"],
    "utilities": ["bills", "utilities", "electric", "internet", "phone bill", "water"],
    "insurance": ["insurance"],
    "education_childcare": ["school", "tuition", "textbook", "course"],
}
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]
WAIT_RE = re.compile(r"\b(wait|payday|next month|later|postpone|tomorrow)\b", re.I)


class Assistant:
    def __init__(self):
        self.model = joblib.load(MODELS_DIR / "intent.joblib")

    def intent(self, text: str):
        proba = self.model.predict_proba([text])[0]
        i = proba.argmax()
        return self.model.classes_[i], float(proba[i])


def find_category(text: str):
    low = text.lower()
    for cat, words in CATEGORY_WORDS.items():
        if any(w in low for w in words):
            return cat
    return None


def find_amount(text: str):
    m = re.search(r"\$\s?(\d[\d,]*(?:\.\d+)?)|(\d[\d,]*(?:\.\d+)?)\s?(?:dollars|bucks|usd)", text.lower())
    return float((m.group(1) or m.group(2)).replace(",", "")) if m else None


def find_month(text: str, today: pd.Timestamp) -> pd.Period:
    low, cur = text.lower(), today.to_period("M")
    if "last month" in low:
        return cur - 1
    for i, name in enumerate(MONTHS, start=1):
        pattern = r"\bin may\b" if name == "may" else r"\b(" + name + "|" + name[:3] + r")\b"
        if re.search(pattern, low):
            p = pd.Period(year=today.year, month=i, freq="M")
            return p if p <= cur else p - 12
    return cur


def find_item(text: str) -> str:
    m = re.search(r"(?:buy|get|afford|purchase|order)\s+(?:a |an |the |new |some )*([a-z0-9 \-']{2,40}?)(?:\s+for\b|\?|$|,)",
                  text.lower())
    return m.group(1).strip() if m else ""


def about_me(text: str) -> bool:
    return bool(re.search(r"\b(i|my|me)\b", text.lower())) and not re.search(r"\b(we|our|us|family)\b", text.lower())


def answer(assistant: Assistant, text: str, data: dict, context: dict = None) -> dict:
    intent, conf = assistant.intent(text)
    if conf < MIN_CONFIDENCE:
        intent = "help"
    ctx = context or {}
    if ctx.get("price") and WAIT_RE.search(text) and intent in ("help", "can_afford", "budget_left", "spending"):
        intent = "wait"
    reply = HANDLERS[intent](text, data, ctx)
    return {"reply": reply, "intent": intent, "confidence": round(conf, 3)}


def _scope(text, d):
    """Teens asking about 'my' money see their own transactions; otherwise the family's."""
    df = d["room"]["df"]
    if d["member"]["role"] == "teen" and about_me(text):
        return df[df["member_id"] == d["member"]["id"]], "you"
    return df, "the family"


def _spending(text, d, ctx):
    df, who = _scope(text, d)
    today = d["today"]
    cat, month = find_category(text), find_month(text, today)
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
            change = f" That's {abs(diff):.0%} {'more' if diff > 0 else 'less'} than the month before ({money(prev_total)})."
        subject = "You" if who == "you" else "The family"
        return f"{subject} spent {money(total)} on {CATEGORY_NAMES[cat]} {label} ({n} payments).{change}"
    by_cat = (-rows.groupby("category")["amount"].sum()).sort_values(ascending=False)
    top = ", ".join(f"{CATEGORY_NAMES.get(c, c)} {money(v)}" for c, v in by_cat.head(4).items() if v > 0)
    subject = "You" if who == "you" else "The family"
    out = f"{subject} spent {money(by_cat.sum())} {label}. Biggest: {top}."
    if who != "you":
        by_m = (-rows.groupby("member_id")["amount"].sum())
        names = {m["id"]: m["display_name"] for m in d["room"]["members"]}
        parts = [f"{names.get(k, '?')} {money(v)}" for k, v in by_m.sort_values(ascending=False).items() if v > 0]
        out += " By person: " + ", ".join(parts) + "."
    return out


def _verdict_text(r: dict) -> str:
    icon = {"buy": "\U0001F7E2", "think": "\U0001F7E1", "not_worth_it": "\U0001F534"}[r["decision"]]
    lines = [f"{icon} {r['title_text']} — {money(r['price'])} on {r['category_name']}."]
    lines += [f"• {x}" for x in r["reasons"]]
    if r.get("market"):
        m = r["market"]
        lines.append(f"• Similar items cost {money(m['low'])}–{money(m['high'])} (2023 prices).")
    if r.get("reasonable_price"):
        lines.append(f"Reasonable price for you this month: up to {money(r['reasonable_price'])}.")
    elif r.get("no_room_this_month"):
        lines.append(f"No room in this month's {r['category_name']} budget; a fresh month starts {r['next_month_starts']}.")
    return "\n".join(lines)


def _can_afford(text, d, ctx):
    price = find_amount(text) or ctx.get("price")
    if not price:
        return "How much does it cost? For example: “Can I buy a jacket for $120?”"
    item = find_item(text) or ctx.get("title") or ""
    cat = find_category(text) or ctx.get("category")
    return _verdict_text(d["verdict"](item, float(price), ctx.get("url", ""), cat))


def _budget_left(text, d, ctx):
    cat = find_category(text)
    s = finance.month_summary(d["room"]["df"], d["state"], d["overspend"], d["today"], d["room"]["limits"])
    cats = {c["category"]: c for c in s["categories"]}
    if cat and cat in cats and cats[cat]["budget"] is not None:
        c = cats[cat]
        left = c["budget"] - c["spent"]
        lead = (f"{money(left)} left of the family's usual {money(c['budget'])} for {c['name']}" if left >= 0
                else f"Already {money(-left)} over the family's usual {money(c['budget'])} for {c['name']}")
        return f"{lead}, with {s['days_left']} days to go. Chance of ending the month over: {c['overspend_probability']:.0%}."
    risky = sorted([c for c in s["categories"] if c["overspend_probability"] is not None],
                   key=lambda c: -c["overspend_probability"])
    lines = [f"• {c['name']}: {money(c['spent'])} of {money(c['budget'])}, risk {c['overspend_probability']:.0%}"
             for c in risky[:4]]
    return f"{s['days_left']} days left this month. Highest overspending risk:\n" + "\n".join(lines)


def _goals(text, d, ctx):
    today, df = d["today"], d["room"]["df"]
    free = finance.monthly_free_cash(df, today)
    family = finance.plan_goals([g for g in d["room"]["goals"] if g["member_id"] is None], free, today)
    mine = [finance.plan_goal(g, today) for g in d["room"]["goals"] if g["member_id"] == d["member"]["id"]]
    lines = []
    for p in family:
        status = "on track ✅" if p["on_track"] else "behind ⚠️"
        lines.append(f"• {p['name']}: {money(p['saved'])} of {money(p['target'])}, needs {money(p['needed_per_month'])}/month, "
                     f"reached {p['projected_date']} ({status}).")
    for p in mine:
        lines.append(f"• Your goal {p['name']}: {money(p['saved'])} of {money(p['target'])}, "
                     f"save {money(p['needed_per_month'])}/month to make it by {p['deadline']}.")
    if not lines:
        return "No goals yet. Add one on the Goals page."
    tail = f"\nThe family keeps about {money(free)} a month after spending."
    behind = [p for p in family if not p["on_track"]]
    if behind:
        gap = sum(p["needed_per_month"] - p["allocated_per_month"] for p in behind)
        tail += f" To get every family goal on track you need about {money(gap)} more per month."
    return "\n".join(lines) + tail


def _where_losing(text, d, ctx):
    df, today = d["room"]["df"], d["today"]
    last_full = today.to_period("M") - 1
    monthly = (-finance.spending(df).groupby(["month", "category"])["amount"].sum()).unstack(fill_value=0.0)
    hist = monthly.loc[(monthly.index < last_full) & (monthly.index >= last_full - 6)]
    if last_full not in monthly.index or hist.empty:
        return "I need a few months of history to see where money goes."
    usual = hist.median()
    diff = (monthly.loc[last_full] - usual).sort_values(ascending=False)
    lines = [f"• {CATEGORY_NAMES.get(c, c)}: {money(monthly.loc[last_full, c])} vs usual {money(usual[c])} (+{money(v)})"
             for c, v in diff.items() if v > 20][:3]
    wants = [c for c, k in d["room"]["kinds"].items() if k == "want" and c in monthly.columns] or \
            [c for c in ("dining", "shopping", "entertainment", "subscriptions", "travel", "personal_care") if c in monthly.columns]
    income = finance.family_income(df[df["month"] == last_full])["amount"].sum()
    out = [f"In {last_full.strftime('%B')}, these grew the most compared with a usual month:"] + (lines or ["• nothing unusual"])
    if income > 0:
        out.append(f"Wants took {monthly.loc[last_full, wants].sum() / income:.0%} of income (a common guide is 30%).")
    subs = monthly.loc[last_full].get("subscriptions", 0.0)
    if subs > 0:
        out.append(f"Subscriptions: {money(subs)} a month = {money(subs * 12)} a year. Check which ones you still use.")
    return "\n".join(out)


def _postponed(text, d, ctx):
    items = d["postponed"]
    waiting = [i for i in items if i["status"] == "waiting"]
    dropped = [i for i in items if i["status"] == "dropped"]
    if not items:
        return "Nothing postponed yet. When the extension says “Not worth it”, press Postpone."
    out = [f"{len(waiting)} purchase(s) waiting, {money(sum(i['price'] for i in waiting))} not spent yet."]
    out += [f"• {i['title'][:50]}: {money(i['price'])}, reminder {i['remind_on']}" for i in waiting[:5]]
    if dropped:
        out.append(f"You decided not to buy {len(dropped)} item(s) and kept {money(sum(i['price'] for i in dropped))}.")
    return "\n".join(out)


def _upcoming(text, d, ctx):
    items = d["upcoming"]()
    if not items:
        return "No regular payments or plans found for the next 30 days."
    total = sum(-i["amount"] for i in items)
    lines = [f"• {i['date']}: {i['name']} {money(-i['amount'])} ({i['detail']})" for i in items[:8]]
    return f"Next 30 days: {len(items)} payments, about {money(total)} in total.\n" + "\n".join(lines)


def _wait(text, d, ctx):
    r = d["verdict"](ctx.get("title", ""), float(ctx["price"]), ctx.get("url", ""), ctx.get("category"))
    now = f"Buying now: {r['title_text'].lower()}" + (f", risk {r['risk_after']:.0%}" if r.get("risk_after") is not None else "")
    budget = r.get("budget")
    later = (f"From {r['next_month_starts']} a fresh month starts; this would use {r['price'] / budget:.0%} of your usual "
             f"{money(budget)} for {r['category_name']}." if budget else f"From {r['next_month_starts']} a fresh month starts.")
    return f"{now}.\n{later}\nPress Postpone and FinPilot will remind you."


def _help(text, d, ctx):
    return ("I answer questions about your family's money, using your own data:\n"
            "• “How much did we spend on dining last month?”\n"
            "• “Can I buy concert tickets for $100?”\n"
            "• “How much is left for shopping?”\n"
            "• “What bills are coming up?”\n"
            "• “How are our goals?”\n"
            "• “Where are we losing money?”")


HANDLERS = {"spending": _spending, "can_afford": _can_afford, "budget_left": _budget_left, "goals": _goals,
            "where_losing": _where_losing, "postponed": _postponed, "upcoming": _upcoming, "help": _help, "wait": _wait}
