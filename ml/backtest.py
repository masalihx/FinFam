"""Step 4 of FinPilot: backtest of the "buy now or postpone" decision.

We replay every online purchase of $20+ that the families made in the test
months (2026-04..2026-09) as if the extension had been open at checkout.
For each purchase each method says "buy" or "postpone":

- no extension: always buy
- 50/30/20 rule: postpone if "wants" spending this month (with the purchase)
  is above 30% of the family's usual monthly income
- proportion: postpone if (spent so far + purchase) x days_in_month / day > budget x 1.1
- model: postpone if the overspend model's probability (with the purchase) >= its threshold

A purchase is "harmful" when its category ended the month above budget x 1.1.
Money saved = for each family-category-month, the overspend above budget that
the postponed purchases cover (postponed purchases are assumed to move to a
later month; overspend cannot be reduced below zero).

Run from the project root:
    .venv/bin/python ml/backtest.py
"""
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_fscore_support

sys.path.insert(0, str(Path(__file__).parent))
from categories import WANTS  # noqa: E402
from live_features import FamilyState  # noqa: E402
from overspend_features import FORECAST_CATEGORIES, OVER_MARGIN  # noqa: E402

PROCESSED = Path("data/processed")
MODELS = Path("ml/models")
RESULTS = Path("ml/results")
TEST_START = pd.Timestamp("2026-04-01")
MIN_PURCHASE = 20.0
WANTS_SHARE = 0.30
ALERT_SHARES = [0.10, 0.20, 0.30]


def purchases_to_check(tx: pd.DataFrame) -> pd.DataFrame:
    """Online purchases of $20+ in test months, in categories the model forecasts."""
    p = tx[(tx["transaction_date"] >= TEST_START) & (tx["channel"] == "online") & (tx["amount"] <= -MIN_PURCHASE)
           & tx["label"].isin(FORECAST_CATEGORIES) & ~tx["is_fraud"]]
    return p.assign(price=-p["amount"], month=p["transaction_date"].dt.to_period("M"))


def month_outcomes(tx: pd.DataFrame, ex: pd.DataFrame) -> pd.DataFrame:
    """Budget and actual month-end total per family-category-month (from the training table)."""
    out = ex.drop_duplicates(["customer_id", "label", "month"])[["customer_id", "label", "month", "budget", "total"]]
    return out.assign(overspend=(out["total"] - out["budget"] * (1 + OVER_MARGIN)).clip(lower=0))


def wants_to_date(tx: pd.DataFrame) -> pd.Series:
    """Cumulative 'wants' spending within each family-month, by transaction."""
    w = tx[tx["label"].isin(WANTS) & ~tx["is_fraud"]].copy()
    w["month"] = w["transaction_date"].dt.to_period("M")
    w["spend"] = -w["amount"]
    w = w.sort_values(["customer_id", "transaction_date", "transaction_id"])
    w["wants_cum"] = w.groupby(["customer_id", "month"])["spend"].cumsum()
    return w.set_index("transaction_id")["wants_cum"]


def evaluate(df: pd.DataFrame, flag_col: str, outcomes: pd.DataFrame) -> dict:
    y = df["harmful"].to_numpy()
    flags = df[flag_col].to_numpy()
    p, r, f, _ = precision_recall_fscore_support(y, flags, average="binary", zero_division=0)
    postponed = df[df[flag_col]].groupby(["customer_id", "label", "month"])["price"].sum().rename("postponed")
    merged = outcomes.merge(postponed, on=["customer_id", "label", "month"], how="inner")
    saved = float(np.minimum(merged["postponed"], merged["overspend"]).sum())
    family_months = df.groupby(["customer_id", "month"]).ngroups
    return {
        "postponed_purchases": int(flags.sum()),
        "postponed_share": round(float(flags.mean()), 3),
        "precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3),
        "overspend_avoided_usd": round(saved, 2),
        "avoided_per_family_month_usd": round(saved / max(1, family_months), 2),
        "false_alarms": int((flags & (y == 0)).sum()),
    }


def main() -> None:
    tx = pd.read_parquet(PROCESSED / "household_tx.parquet")
    customers = pd.read_parquet(PROCESSED / "customers.parquet").set_index("customer_id")
    ex = pd.read_parquet(PROCESSED / "overspend_examples.parquet")
    bundle = joblib.load(MODELS / "overspend.joblib")
    model, threshold, features = bundle["model"], bundle["threshold"], bundle["features"]

    outcomes = month_outcomes(tx, ex)
    purchases = purchases_to_check(tx).merge(outcomes, on=["customer_id", "label", "month"], how="inner")
    purchases = purchases.assign(harmful=purchases["overspend"] > 0)
    wants_cum = wants_to_date(tx)

    rows = []
    states = {}
    for p in purchases.itertuples():
        if p.customer_id not in states:
            c = customers.loc[p.customer_id]
            states[p.customer_id] = FamilyState(tx[tx["customer_id"] == p.customer_id],
                                                c["household_income"], c["children"])
        # Spending through the purchase day already includes this purchase.
        f = states[p.customer_id].features(p.label, p.transaction_date)
        if f is None:
            continue
        rows.append({"transaction_id": p.transaction_id, **{k: f[k] for k in features},
                     "hist_income": f["hist_income"], "proportion_ratio_": f["proportion_ratio"]})
    feats = pd.DataFrame(rows).set_index("transaction_id")
    # The live budget equals the month table budget; keep the live one for the model.
    df = purchases.drop(columns="budget").set_index("transaction_id").join(feats, how="inner")

    df["prob"] = model.predict_proba(df[features])[:, 1]
    df["flag_model"] = df["prob"] >= threshold
    df["flag_proportion"] = df["proportion_ratio_"] > 1 + OVER_MARGIN
    df["wants_cum"] = wants_cum.reindex(df.index).fillna(0.0)
    df["flag_503020"] = df["wants_cum"] > WANTS_SHARE * df["hist_income"].clip(lower=1.0)
    df["flag_none"] = False
    df = df.reset_index()

    total_overspend = float(outcomes.merge(df[["customer_id", "label", "month"]].drop_duplicates(),
                                           on=["customer_id", "label", "month"])["overspend"].sum())
    results = {
        "setup": {"purchases": int(len(df)), "families": int(df["customer_id"].nunique()),
                  "harmful_share": round(float(df["harmful"].mean()), 3),
                  "months": "2026-04..2026-09", "min_purchase_usd": MIN_PURCHASE, "channel": "online",
                  "total_overspend_in_these_category_months_usd": round(total_overspend, 2)},
        "methods": {
            "no_extension": evaluate(df, "flag_none", outcomes),
            "rule_50_30_20": evaluate(df, "flag_503020", outcomes),
            "proportion": evaluate(df, "flag_proportion", outcomes),
            "model": evaluate(df, "flag_model", outcomes),
        },
    }
    for name, r in results["methods"].items():
        print(f"{name:>14}: postponed {r['postponed_purchases']:>4} ({r['postponed_share']:.0%}), "
              f"precision {r['precision']:.2f}, recall {r['recall']:.2f}, "
              f"avoided ${r['overspend_avoided_usd']:,.0f} (${r['avoided_per_family_month_usd']:.2f}/family-month), "
              f"false alarms {r['false_alarms']}")

    # Fair comparison: every method may postpone the same share of purchases,
    # its riskiest ones by its own score. An extension that warns on every
    # second purchase would be ignored, so small alert budgets matter most.
    score_cols = {"rule_50_30_20": df["wants_cum"] / df["hist_income"].clip(lower=1.0),
                  "proportion": df["proportion_ratio_"], "model": df["prob"]}
    rng = np.random.default_rng(0)
    tiebreak = rng.random(len(df)) * 1e-9
    results["equal_alert_budget"] = {}
    print("Same number of warnings for every method:")
    for share in ALERT_SHARES:
        k = int(round(share * len(df)))
        block = {}
        for name, score in score_cols.items():
            top = np.argsort(-(score.to_numpy() + tiebreak))[:k]
            flag = np.zeros(len(df), dtype=bool)
            flag[top] = True
            block[name] = evaluate(df.assign(_flag=flag), "_flag", outcomes)
        results["equal_alert_budget"][f"{share:.0%}"] = block
        print(f"  postpone {share:.0%}: " + " | ".join(
            f"{n} ${b['avoided_per_family_month_usd']:.0f}/fam-month, precision {b['precision']:.2f}"
            for n, b in block.items()))

    cols =["customer_id", "transaction_date", "label", "price", "description", "prob", "budget", "total"]
    results["error_examples"] = {
        "postponed_but_fine": json.loads(df[df["flag_model"] & ~df["harmful"]].nlargest(3, "prob")[cols]
                                         .to_json(orient="records", date_format="iso")),
        "bought_but_harmful": json.loads(df[~df["flag_model"] & df["harmful"]].nsmallest(3, "prob")[cols]
                                         .to_json(orient="records", date_format="iso")),
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "backtest.json").write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    print(f"Saved {RESULTS / 'backtest.json'}")


if __name__ == "__main__":
    main()
