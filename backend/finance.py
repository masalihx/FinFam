"""Money math done by code (never by a language model): summaries, goals, purchase checks."""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from backend import ml_service
from backend.ml_service import FORECAST_CATEGORIES

AVG_DAYS_IN_MONTH = 30.44
CATEGORY_NAMES = {
    "groceries": "Groceries", "dining": "Dining & coffee", "shopping": "Shopping",
    "transportation": "Transport", "entertainment": "Entertainment", "personal_care": "Personal care",
    "subscriptions": "Subscriptions", "travel": "Travel", "health": "Health", "housing": "Housing",
    "utilities": "Utilities", "insurance": "Insurance", "education_childcare": "Education & childcare",
    "fees": "Bank fees", "income": "Income", "transfer": "Transfers",
}


def tx_frame(rows: list) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["id", "date", "amount", "description", "merchant", "channel",
                                     "category", "category_source", "source"])
    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.to_period("M")
    return df


def spending(df: pd.DataFrame) -> pd.DataFrame:
    """Money out (and returns), excluding transfers between own accounts and income."""
    return df[~df["category"].isin(["income", "transfer"])]


def outside_transfers_out(window: pd.DataFrame, max_days: int = 3) -> float:
    """Money sent out by transfer that did not come back into another own account.

    Paying the credit card or moving money to savings shows up twice (out of one
    account, into another) with the same amount within a few days: those pairs
    are internal. An outgoing transfer without a matching incoming one (rent paid
    by Zelle, money to relatives) really leaves the family.
    """
    tr = window[window["category"] == "transfer"].sort_values("date")
    incoming = tr[tr["amount"] > 0][["date", "amount"]].to_dict("records")
    used = [False] * len(incoming)
    outside = 0.0
    for out in tr[tr["amount"] < 0].itertuples():
        match = next((i for i, inc in enumerate(incoming)
                      if not used[i] and abs(inc["amount"] + out.amount) < 0.01
                      and abs((inc["date"] - out.date).days) <= max_days), None)
        if match is None:
            outside += -out.amount
        else:
            used[match] = True
    return outside


def monthly_free_cash(df: pd.DataFrame, today: pd.Timestamp, months: int = 6) -> float:
    """Average income minus spending (and transfers to other people) over the last full months."""
    cur = today.to_period("M")
    window = df[(df["month"] < cur) & (df["month"] >= cur - months)]
    if window.empty:
        return 0.0
    income = window.loc[window["category"] == "income", "amount"].sum()
    spent = -spending(window)["amount"].sum() + outside_transfers_out(window)
    n = window["month"].nunique()
    return float((income - spent) / max(1, n))


def category_budgets(state, today: pd.Timestamp, overrides: dict) -> dict:
    """Usual level per category (median of last 6 months) or the family's own budget."""
    out = {}
    for cat in FORECAST_CATEGORIES:
        row = state.features(cat, today, 0.0)
        learned = None if row is None else float(row["budget"])
        out[cat] = {"learned": learned, "budget": overrides.get(cat, learned)}
    return out


def month_summary(df: pd.DataFrame, state, overspend, today: pd.Timestamp, overrides: dict) -> dict:
    cur = today.to_period("M")
    this_month = df[df["month"] == cur]
    spent_by_cat = (-spending(this_month).groupby("category")["amount"].sum()).to_dict()

    categories = []
    for cat in FORECAST_CATEGORIES:
        row = ml_service.features_with_budget(state, cat, today, 0.0, overrides.get(cat))
        prob = None if row is None else overspend.probability(row)
        budget = None if row is None else float(row["budget"])
        categories.append({
            "category": cat, "name": CATEGORY_NAMES[cat],
            "spent": round(float(spent_by_cat.get(cat, 0.0)), 2),
            "budget": None if budget is None else round(budget, 2),
            "overspend_probability": None if prob is None else round(prob, 3),
            "light": None if prob is None else overspend.light(prob),
        })

    # Other spending (bills, housing...) shown without a forecast.
    other = {c: round(float(v), 2) for c, v in spent_by_cat.items() if c not in FORECAST_CATEGORIES}

    last = df[(df["month"] >= cur - 6) & (df["month"] <= cur)]
    trend = (-spending(last).groupby(["month", "category"])["amount"].sum()).unstack(fill_value=0.0)
    trend_rows = [{"month": str(m), **{c: round(float(v), 2) for c, v in r.items()}} for m, r in trend.iterrows()]

    income_month = float(this_month.loc[this_month["category"] == "income", "amount"].sum())
    return {
        "today": str(today.date()), "month": str(cur),
        "days_left": int(today.days_in_month - today.day),
        "income_this_month": round(income_month, 2),
        "spent_this_month": round(float(-spending(this_month)["amount"].sum()), 2),
        "free_cash_per_month": round(monthly_free_cash(df, today), 2),
        "categories": categories, "other_spending": other, "trend": trend_rows,
    }


@dataclass
class GoalPlan:
    id: int
    name: str
    target: float
    saved: float
    deadline: str
    months_left: float
    needed_per_month: float
    free_cash_per_month: float
    on_track: bool
    projected_date: str

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        for k in ("target", "saved", "months_left", "needed_per_month", "free_cash_per_month"):
            d[k] = round(d[k], 2)
        d["progress"] = round(self.saved / self.target, 3) if self.target else 0.0
        return d


def plan_goal(goal: dict, free_cash: float, today: pd.Timestamp) -> GoalPlan:
    deadline = pd.Timestamp(goal["deadline"])
    months_left = max(0.0, (deadline - today).days / AVG_DAYS_IN_MONTH)
    remaining = max(0.0, goal["target"] - goal["saved"])
    needed = remaining / months_left if months_left > 0 else remaining
    if free_cash > 0:
        projected = today + pd.Timedelta(days=remaining / free_cash * AVG_DAYS_IN_MONTH)
        projected_date = str(projected.date())
    else:
        projected_date = "never at the current pace"
    return GoalPlan(goal["id"], goal["name"], goal["target"], goal["saved"], goal["deadline"],
                    months_left, needed, free_cash, free_cash >= needed, projected_date)


def plan_goals(goals: list, free_cash: float, today: pd.Timestamp, max_months: int = 600) -> list:
    """Share free cash between goals, earliest deadline first, month by month.

    Every month each goal (by deadline) gets what it needs; money left over goes
    to the next goals. When a goal is reached, its money flows to the others.
    A goal is on track when it is reached by its deadline.
    """
    ordered = sorted(goals, key=lambda g: g["deadline"])
    plans = [plan_goal(g, free_cash, today) for g in ordered]
    remaining = [max(0.0, g["target"] - g["saved"]) for g in ordered]
    done_month = [0 if r == 0 else None for r in remaining]
    first_alloc = [0.0] * len(ordered)
    done_frac = [0.0] * len(ordered)
    for m in range(1, max_months + 1):
        available = max(0.0, free_cash)
        given = [0.0] * len(ordered)
        # First pass: each unfinished goal gets its planned monthly amount.
        for i, plan in enumerate(plans):
            if done_month[i] is None:
                give = min(plan.needed_per_month, remaining[i], available)
                remaining[i] -= give
                available -= give
                given[i] += give
                if m == 1:
                    first_alloc[i] += give
        # Second pass: leftovers speed up the goals in deadline order.
        for i in range(len(plans)):
            if done_month[i] is None and available > 0:
                give = min(remaining[i], available)
                remaining[i] -= give
                available -= give
                given[i] += give
                if m == 1:
                    first_alloc[i] += give
        for i in range(len(plans)):
            if done_month[i] is None and remaining[i] <= 0.005:
                done_month[i] = m
                # Part of the month actually needed for the last payment.
                full = max(plans[i].needed_per_month, given[i], 1e-9)
                done_frac[i] = min(1.0, given[i] / full)
        if all(d is not None for d in done_month) or available == max(0.0, free_cash) == 0:
            break

    out = []
    for i, plan in enumerate(plans):
        d = plan.as_dict()
        if done_month[i] is None:
            d["projected_date"] = "not reached at the current pace"
            d["on_track"] = False
        else:
            months = done_month[i] - 1 + done_frac[i]
            reached = today + pd.Timedelta(days=months * AVG_DAYS_IN_MONTH)
            d["projected_date"] = str(reached.date())
            d["on_track"] = reached <= pd.Timestamp(plan.deadline)
        d["allocated_per_month"] = round(first_alloc[i], 2)
        out.append(d)
    return out


def check_purchase(state, overspend, category: str, price: float, today: pd.Timestamp,
                   budget_override, goals: list, free_cash: float) -> dict:
    before = ml_service.features_with_budget(state, category, today, 0.0, budget_override)
    after = ml_service.features_with_budget(state, category, today, price, budget_override)
    name = CATEGORY_NAMES.get(category, category)

    # Goals arrive ordered by relevance (off-track goals first).
    goal = goals[0] if goals else None
    delay_days = None
    if goal and free_cash > 0:
        delay_days = int(round(price / (free_cash / AVG_DAYS_IN_MONTH)))

    if before is None or after is None:
        return {"light": "green", "category": category, "category_name": name, "probability_before": None,
                "probability_after": None, "goal": goal and goal["name"], "goal_delay_days": delay_days,
                "reason": f"Not enough history for {name} yet, so FinPilot cannot judge this purchase.",
                "spent_so_far": None, "budget": None}

    p0, p1 = overspend.probability(before), overspend.probability(after)
    light = overspend.light(p1)
    spent = float(before["spent_to_date"])
    budget = float(before["budget"])
    parts = [f"{name}: ${spent:,.0f} spent of your usual ${budget:,.0f} this month."]
    parts.append(f"With this ${price:,.0f} purchase, the chance of going over rises from "
                 f"{p0:.0%} to {p1:.0%}." if p1 > p0 + 0.005 else
                 f"Chance of going over this month: {p1:.0%}.")
    if goal and delay_days:
        parts.append(f"Your goal “{goal['name']}” would move about {delay_days} day"
                     f"{'s' if delay_days != 1 else ''} later.")
    if light == "red":
        parts.append("Better to postpone until next month.")
    elif light == "yellow":
        parts.append("Think it over: do you need it this month?")

    return {"light": light, "category": category, "category_name": name,
            "probability_before": round(p0, 3), "probability_after": round(p1, 3),
            "spent_so_far": round(spent, 2), "budget": round(budget, 2),
            "goal": goal and goal["name"], "goal_delay_days": delay_days, "reason": " ".join(parts)}


def next_month_start(today: pd.Timestamp) -> str:
    return str((today.to_period("M") + 1).to_timestamp().date())


def safe_float(x) -> float:
    return float(np.nan_to_num(x))
