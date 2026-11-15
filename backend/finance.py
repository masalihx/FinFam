"""Money math done by code (never by a language model)."""
import numpy as np
import pandas as pd

from backend import ml_service
from backend.ml_service import FORECAST_CATEGORIES

AVG_DAYS_IN_MONTH = 30.44
CATEGORY_NAMES = {
    "groceries": "Groceries", "dining": "Dining & coffee", "shopping": "Shopping", "transportation": "Transport",
    "entertainment": "Entertainment", "personal_care": "Personal care", "subscriptions": "Subscriptions",
    "travel": "Travel", "health": "Health", "housing": "Housing", "utilities": "Utilities", "insurance": "Insurance",
    "education_childcare": "Education & childcare", "fees": "Bank fees", "income": "Income", "transfer": "Transfers",
}
TX_COLUMNS = ["id", "room_id", "member_id", "date", "amount", "description", "merchant", "channel", "category",
              "category_source", "source"]


def money(x: float) -> str:
    return ("−$" if x < 0 else "$") + f"{abs(x):,.0f}"


def tx_frame(rows: list) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=TX_COLUMNS)
    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.to_period("M")
    return df


def spending(df: pd.DataFrame) -> pd.DataFrame:
    return df[~df["category"].isin(["income", "transfer"])]


def outside_transfers_out(window: pd.DataFrame, max_days: int = 3) -> float:
    """Transfers that left the family (an internal move appears twice: out of one account, into another)."""
    tr = window[window["category"] == "transfer"].sort_values("date")
    incoming = tr[tr["amount"] > 0][["date", "amount"]].to_dict("records")
    used = [False] * len(incoming)
    outside = 0.0
    for out in tr[tr["amount"] < 0].itertuples():
        match = next((i for i, inc in enumerate(incoming) if not used[i] and abs(inc["amount"] + out.amount) < 0.01
                      and abs((inc["date"] - out.date).days) <= max_days), None)
        if match is None:
            outside += -out.amount
        else:
            used[match] = True
    return outside


def family_income(df: pd.DataFrame) -> pd.DataFrame:
    """Income rows, without allowance (money moving inside the family)."""
    return df[(df["category"] == "income") & (df["source"] != "allowance")]


def monthly_free_cash(df: pd.DataFrame, today: pd.Timestamp, months: int = 6) -> float:
    """Average income minus spending (and money sent to other people) over the last full months."""
    cur = today.to_period("M")
    window = df[(df["month"] < cur) & (df["month"] >= cur - months) & (df["source"] != "allowance")]
    if window.empty:
        return 0.0
    income = family_income(window)["amount"].sum()
    spent = -spending(window)["amount"].sum() + outside_transfers_out(window)
    return float((income - spent) / max(1, window["month"].nunique()))


def plan_goal(goal: dict, today: pd.Timestamp) -> dict:
    deadline = pd.Timestamp(goal["deadline"])
    months_left = max(0.0, (deadline - today).days / AVG_DAYS_IN_MONTH)
    remaining = max(0.0, goal["target"] - goal["saved"])
    needed = remaining / months_left if months_left > 0 else remaining
    return {**goal, "months_left": round(months_left, 1), "needed_per_month": round(needed, 2),
            "progress": round(goal["saved"] / goal["target"], 3) if goal["target"] else 0.0}


def plan_goals(goals: list, free_cash: float, today: pd.Timestamp, max_months: int = 600) -> list:
    """Share free cash between goals month by month, nearest deadline first."""
    ordered = sorted(goals, key=lambda g: g["deadline"])
    plans = [plan_goal(g, today) for g in ordered]
    remaining = [max(0.0, g["target"] - g["saved"]) for g in ordered]
    done = [0.0 if r == 0 else None for r in remaining]
    first = [0.0] * len(plans)
    for m in range(1, max_months + 1):
        available, given = max(0.0, free_cash), [0.0] * len(plans)
        for i, p in enumerate(plans):  # each goal gets what it needs
            if done[i] is None:
                g = min(p["needed_per_month"], remaining[i], available)
                remaining[i] -= g
                available -= g
                given[i] += g
        for i in range(len(plans)):    # leftovers speed up the next goals
            if done[i] is None and available > 0:
                g = min(remaining[i], available)
                remaining[i] -= g
                available -= g
                given[i] += g
        if m == 1:
            first = given[:]
        for i in range(len(plans)):
            if done[i] is None and remaining[i] <= 0.005:
                done[i] = m - 1 + min(1.0, given[i] / max(plans[i]["needed_per_month"], given[i], 1e-9))
        if all(d is not None for d in done) or free_cash <= 0:
            break
    out = []
    for i, p in enumerate(plans):
        if done[i] is None:
            p.update(projected_date="not reached at the current pace", on_track=False)
        else:
            reached = today + pd.Timedelta(days=done[i] * AVG_DAYS_IN_MONTH)
            p.update(projected_date=str(reached.date()),
                     on_track=bool(reached.normalize() <= pd.Timestamp(p["deadline"]).normalize()))
        p["allocated_per_month"] = round(first[i], 2)
        out.append(p)
    return out


def month_summary(df, state, overspend, today, limits: dict) -> dict:
    cur = today.to_period("M")
    this_month = df[df["month"] == cur]
    spent_by_cat = (-spending(this_month).groupby("category")["amount"].sum()).to_dict()
    cats = []
    for cat in FORECAST_CATEGORIES:
        row = ml_service.features_with_budget(state, cat, today, 0.0, limits.get(cat))
        prob = None if row is None else overspend.probability(row)
        budget = None if row is None else float(row["budget"])
        rest = None if row is None else float(row["hist_after_day_ratio"]) * budget
        cats.append({
            "category": cat, "name": CATEGORY_NAMES[cat], "spent": round(float(spent_by_cat.get(cat, 0.0)), 2),
            "budget": None if budget is None else round(budget, 2), "limit_set_by_family": cat in limits,
            "expected_rest_of_month": None if rest is None else round(rest, 2),
            "overspend_probability": None if prob is None else round(prob, 3),
            "light": None if prob is None else ("red" if prob >= 0.75 else "yellow" if prob >= overspend.threshold else "green"),
        })
    other = {c: round(float(v), 2) for c, v in spent_by_cat.items() if c not in FORECAST_CATEGORIES and v > 0}
    last = df[(df["month"] >= cur - 5) & (df["month"] <= cur)]
    trend = (-spending(last).groupby(["month", "category"])["amount"].sum()).unstack(fill_value=0.0)
    return {
        "today": str(today.date()), "month": str(cur), "days_left": int(today.days_in_month - today.day),
        "income_this_month": round(float(family_income(this_month)["amount"].sum()), 2),
        "spent_this_month": round(float(-spending(this_month)["amount"].sum()), 2),
        "free_cash_per_month": round(monthly_free_cash(df, today), 2),
        "categories": cats, "other_spending": other,
        "trend": [{"month": str(m), **{c: round(float(v), 2) for c, v in r.items()}} for m, r in trend.iterrows()],
    }


def usual_p90(df: pd.DataFrame, category: str, today: pd.Timestamp):
    """90th percentile of the family's single purchases in a category over the last 12 months."""
    h = df[(df["category"] == category) & (df["amount"] < -5) & (df["date"] < today)
           & (df["date"] >= today - pd.DateOffset(months=12))]
    return float(np.quantile(-h["amount"], 0.9)) if len(h) >= 5 else None


def setup_suggestions(df: pd.DataFrame, recurring_by_category: dict, today: pd.Timestamp) -> list:
    """ML suggestions for the start screen: each category as need or want, with a monthly amount."""
    cur = today.to_period("M")
    window = spending(df[(df["month"] < cur) & (df["month"] >= cur - 6)])
    if window.empty:
        return []
    monthly = (-window.groupby(["month", "category"])["amount"].sum()).unstack(fill_value=0.0)
    out = []
    for cat in monthly.columns:
        med = float(monthly[cat].median())
        if med < 5:
            continue
        regular = recurring_by_category.get(cat, [])
        kind = ml_service.default_kind(cat)
        if kind == "other":
            kind = "need" if regular else "want"
        if regular:
            why = "Regular payments: " + ", ".join(regular[:3])
        else:
            why = "Bills and essentials" if kind == "need" else "Day-to-day choices you can adjust"
        out.append({"category": cat, "name": CATEGORY_NAMES.get(cat, cat), "kind": kind,
                    "usual_per_month": round(med, 2), "suggested_limit": round(med, 2) if kind == "want" else None,
                    "why": why})
    return sorted(out, key=lambda x: (x["kind"] != "need", -x["usual_per_month"]))
