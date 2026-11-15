"""Recurring payments: grouping and features, shared by training and the web app.

A "series" is all transactions of one family with the same merchant key and
direction (money in / money out). The model decides whether a series is a
regular payment (rent, salary, phone bill, subscription) and the code predicts
the next date and amount.
"""
import re

import numpy as np
import pandas as pd

from text_utils import normalize

SERIES_FEATURES = [
    "n", "n_months", "month_coverage", "gap_median", "gap_cv", "gap_near_month", "gap_near_week",
    "gap_near_2weeks", "amount_log", "amount_cv", "amount_same_share", "day_of_month_std", "is_inflow",
    "span_days",
]


def merchant_key(description: str) -> str:
    """Merchant name without dates, card numbers, confirmation codes and bank wrappers."""
    tokens = [t for t in normalize(description).split() if "0" not in t and not re.fullmatch(r"\W+", t)]
    tokens = [t for t in tokens if t not in ("[debit]", "[credit]")]
    return " ".join(tokens[:6])


def add_keys(tx: pd.DataFrame) -> pd.DataFrame:
    return tx.assign(key=tx["description"].map(merchant_key), is_inflow=tx["amount"] > 0)


def series_features(group: pd.DataFrame, months_observed: int) -> dict:
    """Features of one series (transactions sorted by date)."""
    dates = group["date"].sort_values()
    gaps = dates.diff().dt.days.dropna().to_numpy()
    amounts = group["amount"].abs().to_numpy()
    gm = float(np.median(gaps)) if len(gaps) else 0.0
    n_months = dates.dt.to_period("M").nunique()
    near = lambda target, tol: float(np.mean(np.abs(gaps - target) <= tol)) if len(gaps) else 0.0  # noqa: E731
    med_amount = float(np.median(amounts))
    return {
        "n": len(group),
        "n_months": n_months,
        "month_coverage": n_months / max(1, months_observed),
        "gap_median": gm,
        "gap_cv": float(np.std(gaps) / gm) if len(gaps) > 1 and gm > 0 else 3.0,
        "gap_near_month": near(30.4, 4),
        "gap_near_week": near(7, 1),
        "gap_near_2weeks": near(14, 2),
        "amount_log": float(np.log1p(med_amount)),
        "amount_cv": float(np.std(amounts) / med_amount) if med_amount > 0 else 0.0,
        "amount_same_share": float(np.mean(np.abs(amounts - med_amount) <= 0.01 * max(med_amount, 1))),
        "day_of_month_std": float(np.std(dates.dt.day)),
        "is_inflow": float(group["is_inflow"].iloc[0]),
        "span_days": float((dates.max() - dates.min()).days),
    }


def build_series(tx: pd.DataFrame, family_col: str = "customer_id", min_n: int = 2) -> pd.DataFrame:
    """One row per (family, merchant key, direction) with features and summary info."""
    tx = add_keys(tx)
    rows = []
    for fam, ftx in tx.groupby(family_col):
        months_observed = ftx["date"].dt.to_period("M").nunique()
        for (key, inflow), g in ftx.groupby(["key", "is_inflow"]):
            if len(g) < min_n or not key:
                continue
            g = g.sort_values("date")
            row = series_features(g, months_observed)
            row.update({family_col: fam, "key": key, "last_date": g["date"].max(),
                        "last_amount": float(g["amount"].iloc[-1]), "median_amount": float(g["amount"].tail(3).median()),
                        "example": g["description"].iloc[-1]})
            if "stream_id" in g:
                row["label"] = int(g["stream_id"].notna().mean() > 0.5)
            rows.append(row)
    return pd.DataFrame(rows)


def next_occurrence(last_date: pd.Timestamp, gap_median: float, after: pd.Timestamp) -> pd.Timestamp:
    """Next expected date after `after`, stepping by the usual gap (monthly series snap to the same day)."""
    if 26 <= gap_median <= 35:
        d = last_date
        while d <= after:
            d = d + pd.DateOffset(months=1)
        return d
    step = pd.Timedelta(days=max(1.0, round(gap_median)))
    d = last_date
    while d <= after:
        d = d + step
    return d
