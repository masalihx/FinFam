"""Features for the overspend forecast (ML 2), shared by training and the web app.

Question the model answers: on day d of a month, will this family's spending
in category c end the month above its usual level (its "budget")?

- Budget = median monthly spending in c over the previous 6 months
  (at least 3 months of history needed). The family can override it in the app.
- Overspend = month-end spending > budget * (1 + OVER_MARGIN).
- Everything the model sees is known on day d; nothing from later days.
"""
import numpy as np
import pandas as pd

FORECAST_CATEGORIES = ["groceries", "dining", "shopping", "transportation", "entertainment",
                       "personal_care", "subscriptions", "travel", "health"]
CHECK_DAYS = [5, 10, 15, 20, 25]
HISTORY_MONTHS = 6
MIN_HISTORY = 3
OVER_MARGIN = 0.10

FEATURES = [
    "day", "days_in_month", "days_left", "spent_to_date", "budget", "spent_ratio",
    "proportion_ratio", "pace_ratio", "hist_after_day_ratio", "hist_mean_ratio",
    "hist_std_ratio", "hist_max_ratio", "hist_over_share", "n_tx_to_date", "n_tx_ratio",
    "income_to_date_ratio", "month_of_year", "category_code", "household_income", "children",
]
# The model must never say that spending more lowers the risk.
MONOTONE = {"spent_to_date": 1, "spent_ratio": 1, "proportion_ratio": 1}


def monthly_daily_spend(tx: pd.DataFrame) -> pd.DataFrame:
    """Spending per family, category, month and day of month (purchases minus returns)."""
    spend = tx[tx["label"].isin(FORECAST_CATEGORIES) & ~tx["is_fraud"]].copy()
    spend["month"] = spend["transaction_date"].dt.to_period("M")
    spend["day"] = spend["transaction_date"].dt.day
    spend["spend"] = -spend["amount"]
    return (spend.groupby(["customer_id", "label", "month", "day"])
            .agg(spend=("spend", "sum"), n_tx=("spend", "size")).reset_index())


def monthly_income(tx: pd.DataFrame) -> pd.DataFrame:
    """Income per family, month and day of month."""
    inc = tx[tx["label"].eq("income")].copy()
    inc["month"] = inc["transaction_date"].dt.to_period("M")
    inc["day"] = inc["transaction_date"].dt.day
    return inc.groupby(["customer_id", "month", "day"])["amount"].sum().rename("income").reset_index()


def _cum_by_day(daily: pd.DataFrame, keys: list, value: str, days: list) -> pd.DataFrame:
    """Cumulative value up to and including each check day, for every key group."""
    rows = []
    for d in days:
        part = daily[daily["day"] <= d].groupby(keys)[value].sum().rename(f"{value}_to_{d}")
        rows.append(part)
    return pd.concat(rows, axis=1).fillna(0.0)


def build_examples(tx: pd.DataFrame, customers: pd.DataFrame) -> pd.DataFrame:
    """One row per (family, category, month, check day) with features and the label."""
    daily = monthly_daily_spend(tx)
    keys = ["customer_id", "label", "month"]

    totals = daily.groupby(keys).agg(total=("spend", "sum"), n_tx_total=("n_tx", "sum"))
    cum = _cum_by_day(daily, keys, "spend", CHECK_DAYS)
    cnt = _cum_by_day(daily, keys, "n_tx", CHECK_DAYS)
    month_tbl = totals.join(cum).join(cnt).reset_index()

    # Fill months with zero spending so history is not biased upward.
    months_per_family = tx.assign(month=tx["transaction_date"].dt.to_period("M")) \
        .groupby("customer_id")["month"].agg(["min", "max"])
    grid = []
    for cid, row in months_per_family.iterrows():
        months = pd.period_range(row["min"], row["max"], freq="M")
        for cat in FORECAST_CATEGORIES:
            grid.append(pd.DataFrame({"customer_id": cid, "label": cat, "month": months}))
    grid = pd.concat(grid, ignore_index=True)
    month_tbl = grid.merge(month_tbl, on=keys, how="left").fillna(0.0)
    month_tbl = month_tbl.sort_values(keys).reset_index(drop=True)

    income = monthly_income(tx)
    inc_cum = _cum_by_day(income, ["customer_id", "month"], "income", CHECK_DAYS)
    inc_total = income.groupby(["customer_id", "month"])["income"].sum().rename("income_total")
    inc_tbl = inc_cum.join(inc_total).reset_index()

    # History features: previous months only (shift by one month).
    g = month_tbl.groupby(["customer_id", "label"])
    prev = lambda s: s.shift(1).rolling(HISTORY_MONTHS, min_periods=MIN_HISTORY)  # noqa: E731
    month_tbl["budget"] = g["total"].transform(lambda s: prev(s).median())
    month_tbl["hist_mean"] = g["total"].transform(lambda s: prev(s).mean())
    month_tbl["hist_std"] = g["total"].transform(lambda s: prev(s).std())
    month_tbl["hist_max"] = g["total"].transform(lambda s: prev(s).max())
    month_tbl["hist_n_tx"] = g["n_tx_total"].transform(lambda s: prev(s).mean())
    for d in CHECK_DAYS:
        month_tbl[f"hist_to_{d}"] = g[f"spend_to_{d}"].transform(lambda s: prev(s).mean())

    month_tbl = month_tbl.merge(inc_tbl, on=["customer_id", "month"], how="left").fillna(
        {c: 0.0 for c in inc_tbl.columns if c not in ("customer_id", "month")})
    hist_income = month_tbl.groupby(["customer_id", "label"])["income_total"].transform(
        lambda s: prev(s).mean())
    month_tbl["hist_income"] = hist_income

    # Over-budget share in history needs the budget of each earlier month.
    month_tbl["was_over"] = (month_tbl["total"] > month_tbl["budget"] * (1 + OVER_MARGIN)).astype(float)
    month_tbl.loc[month_tbl["budget"].isna(), "was_over"] = np.nan
    month_tbl["hist_over_share"] = month_tbl.groupby(["customer_id", "label"])["was_over"].transform(
        lambda s: s.shift(1).rolling(HISTORY_MONTHS, min_periods=1).mean()).fillna(0.0)

    month_tbl = month_tbl[month_tbl["budget"].notna() & (month_tbl["budget"] > 1.0)]

    rows = []
    for d in CHECK_DAYS:
        part = month_tbl.copy()
        part["day"] = d
        part["spent_to_date"] = part[f"spend_to_{d}"]
        part["n_tx_to_date"] = part[f"n_tx_to_{d}"]
        part["hist_to_day"] = part[f"hist_to_{d}"]
        part["income_to_date"] = part[f"income_to_{d}"]
        rows.append(part)
    ex = pd.concat(rows, ignore_index=True)

    ex["days_in_month"] = ex["month"].dt.days_in_month
    ex = ex.merge(customers[["customer_id", "household_income", "children"]], on="customer_id", how="left")
    ex["is_over"] = (ex["total"] > ex["budget"] * (1 + OVER_MARGIN)).astype(int)
    return add_features(ex)


def add_features(ex: pd.DataFrame) -> pd.DataFrame:
    """Ratios and derived features. Works for training rows and live app rows."""
    b = ex["budget"].clip(lower=1.0)
    ex = ex.copy()
    ex["days_left"] = ex["days_in_month"] - ex["day"]
    ex["spent_ratio"] = ex["spent_to_date"] / b
    ex["proportion_ratio"] = ex["spent_to_date"] * ex["days_in_month"] / ex["day"] / b
    ex["pace_ratio"] = ex["spent_to_date"] / ex["hist_to_day"].clip(lower=1.0)
    ex["hist_after_day_ratio"] = (ex["hist_mean"] - ex["hist_to_day"]).clip(lower=0) / b
    ex["hist_mean_ratio"] = ex["hist_mean"] / b
    ex["hist_std_ratio"] = ex["hist_std"].fillna(0) / b
    ex["hist_max_ratio"] = ex["hist_max"] / b
    ex["n_tx_ratio"] = ex["n_tx_to_date"] / ex["hist_n_tx"].clip(lower=1.0)
    ex["income_to_date_ratio"] = ex["income_to_date"] / ex["hist_income"].clip(lower=1.0)
    ex["month_of_year"] = ex["month"].dt.month
    ex["category_code"] = ex["label"].map({c: i for i, c in enumerate(FORECAST_CATEGORIES)})
    return ex
