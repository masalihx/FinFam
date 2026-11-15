"""Overspend features for any day, computed from one family's transactions.

Used by the backtest and by the web app ("can I buy this now?").
Matches `overspend_features.build_examples` on the check days (tested in
`ml/check_live_features.py`), but works on every day of the month.
"""
import numpy as np
import pandas as pd

from overspend_features import FORECAST_CATEGORIES, HISTORY_MONTHS, MIN_HISTORY, OVER_MARGIN, add_features


class FamilyState:
    """Daily spending and income of one family, ready for fast lookups."""

    def __init__(self, fam_tx: pd.DataFrame, household_income: float, children: float):
        self.household_income = household_income
        self.children = children
        months = fam_tx["transaction_date"].dt.to_period("M")
        self.first_month = months.min()

        spend = fam_tx[fam_tx["label"].isin(FORECAST_CATEGORIES) & ~fam_tx["is_fraud"]]
        spend = spend.assign(month=spend["transaction_date"].dt.to_period("M"),
                             day=spend["transaction_date"].dt.day, spend=-spend["amount"])
        self.spend = spend.groupby(["label", "month", "day"]).agg(
            spend=("spend", "sum"), n_tx=("spend", "size")).sort_index()

        inc = fam_tx[fam_tx["label"].eq("income")]
        inc = inc.assign(month=inc["transaction_date"].dt.to_period("M"), day=inc["transaction_date"].dt.day)
        self.income = inc.groupby(["month", "day"])["amount"].sum().sort_index()

    def _month_spend(self, category: str, month: pd.Period) -> pd.DataFrame:
        try:
            return self.spend.loc[(category, month)]
        except KeyError:
            return pd.DataFrame(columns=["spend", "n_tx"], index=pd.Index([], name="day"))

    def _month_income(self, month: pd.Period) -> pd.Series:
        try:
            return self.income.loc[month]
        except KeyError:
            return pd.Series(dtype=float)

    def history(self, category: str, month: pd.Period):
        """Totals of the previous months (zeros for months with no spending)."""
        start = max(self.first_month, month - HISTORY_MONTHS)
        prev_months = pd.period_range(start, month - 1, freq="M") if start <= month - 1 else []
        return list(prev_months)

    def features(self, category: str, as_of: pd.Timestamp, extra_amount: float = 0.0):
        """Feature row on day `as_of` with `extra_amount` added to spending so far.

        Returns None when there is not enough history to know the family's usual level.
        """
        month = as_of.to_period("M")
        day = as_of.day
        prev_months = self.history(category, month)
        if len(prev_months) < MIN_HISTORY:
            return None

        totals, to_day, n_totals = [], [], []
        incomes = []
        for m in prev_months:
            ms = self._month_spend(category, m)
            totals.append(float(ms["spend"].sum()))
            to_day.append(float(ms.loc[ms.index <= day, "spend"].sum()))
            n_totals.append(float(ms["n_tx"].sum()))
            incomes.append(float(self._month_income(m).sum()))
        totals = np.array(totals)
        budget = float(np.median(totals))
        if budget <= 1.0:
            return None

        cur = self._month_spend(category, month)
        cur = cur[cur.index <= day]
        cur_inc = self._month_income(month)
        row = {
            "label": category, "month": month, "day": day, "days_in_month": as_of.days_in_month,
            "spent_to_date": float(cur["spend"].sum()) + extra_amount,
            "n_tx_to_date": float(cur["n_tx"].sum()) + (1 if extra_amount > 0 else 0),
            "budget": budget,
            "hist_mean": float(totals.mean()),
            "hist_std": float(totals.std(ddof=1)) if len(totals) > 1 else 0.0,
            "hist_max": float(totals.max()),
            "hist_n_tx": float(np.mean(n_totals)),
            "hist_to_day": float(np.mean(to_day)),
            "hist_over_share": float((totals > budget * (1 + OVER_MARGIN)).mean()),
            "income_to_date": float(cur_inc[cur_inc.index <= day].sum()),
            "hist_income": float(np.mean(incomes)),
            "household_income": self.household_income,
            "children": self.children,
        }
        return add_features(pd.DataFrame([row])).iloc[0]
