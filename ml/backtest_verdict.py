"""ML part 5 check: backtest of the full verdict on real purchases.

Same replay as ml/backtest.py: every online purchase of $20+ in the test months
(2026-04..09). The verdict uses the signals that exist for bank purchases:
overspend risk (part 3) and the family's usual prices. Bank lines have no product
title, so the market-price and goal checks are not part of this backtest.

Comparison at the same number of warnings: the 50/30/20 rule and the proportion
rule each postpone their own riskiest purchases, as many as the verdict does.

Run from the project root:
    .venv/bin/python ml/backtest_verdict.py
"""
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from backtest import evaluate, month_outcomes, purchases_to_check, wants_to_date  # noqa: E402
from categories import NEEDS  # noqa: E402
from live_features import FamilyState  # noqa: E402
from overspend_features import OVER_MARGIN  # noqa: E402
from verdict import Signals, decide  # noqa: E402

PROCESSED = Path("data/processed")
RESULTS = Path("ml/results")


def usual_p90(tx: pd.DataFrame, customer: str, category: str, before: pd.Timestamp):
    """90th percentile of the family's single purchases in a category over the 12 months before."""
    h = tx[(tx["customer_id"] == customer) & (tx["label"] == category) & (tx["amount"] < -5)
           & (tx["transaction_date"] < before) & (tx["transaction_date"] >= before - pd.DateOffset(months=12))]
    return float(np.quantile(-h["amount"], 0.9)) if len(h) >= 5 else None


def main() -> None:
    tx = pd.read_parquet(PROCESSED / "household_tx.parquet")
    customers = pd.read_parquet(PROCESSED / "customers.parquet").set_index("customer_id")
    ex = pd.read_parquet(PROCESSED / "overspend_examples.parquet")
    bundle = joblib.load("ml/models/overspend.joblib")
    model, threshold, features = bundle["model"], bundle["threshold"], bundle["features"]

    outcomes = month_outcomes(tx, ex)
    purchases = purchases_to_check(tx).merge(outcomes, on=["customer_id", "label", "month"], how="inner")
    purchases = purchases.assign(harmful=purchases["overspend"] > 0)
    wants_cum = wants_to_date(tx)

    rows, states = [], {}
    for p in purchases.itertuples():
        if p.customer_id not in states:
            c = customers.loc[p.customer_id]
            states[p.customer_id] = FamilyState(tx[tx["customer_id"] == p.customer_id], c["household_income"], c["children"])
        st = states[p.customer_id]
        after = st.features(p.label, p.transaction_date)
        before = st.features(p.label, p.transaction_date, extra_amount=-p.price)
        if after is None or before is None:
            continue
        r_after = float(model.predict_proba(pd.DataFrame([after[features]]))[0, 1])
        r_before = float(model.predict_proba(pd.DataFrame([before[features]]))[0, 1])
        p90 = usual_p90(tx, p.customer_id, p.label, p.transaction_date)
        v = decide(Signals(price=p.price, category_name=p.label, is_need=p.label in NEEDS, risk_before=r_before,
                           risk_after=r_after, warn_threshold=threshold, usual_p90=p90))
        rows.append({"transaction_id": p.transaction_id, "decision": v.decision, "risk": r_after,
                     "proportion": float(after["proportion_ratio"]), "hist_income": float(after["hist_income"]),
                     "above_usual": v.checks.get("above_usual", False), "high_risk": v.checks.get("high_risk", False)})
    feats = pd.DataFrame(rows).set_index("transaction_id")
    df = purchases.set_index("transaction_id").join(feats, how="inner")
    df["wants_cum"] = wants_cum.reindex(df.index).fillna(0.0)
    df = df.reset_index()

    df["flag_verdict"] = df["decision"] == "not_worth_it"
    df["flag_verdict_or_think"] = df["decision"] != "buy"
    k = int(df["flag_verdict"].sum())
    rng = np.random.default_rng(0)
    tie = rng.random(len(df)) * 1e-9

    def top_k(score):
        flag = np.zeros(len(df), dtype=bool)
        flag[np.argsort(-(score.to_numpy() + tie))[:k]] = True
        return flag

    df["flag_503020"] = top_k(df["wants_cum"] / df["hist_income"].clip(lower=1.0))
    df["flag_proportion"] = top_k(df["proportion"])
    df["flag_risk_only"] = top_k(df["risk"])

    results = {
        "setup": {"purchases": int(len(df)), "families": int(df["customer_id"].nunique()),
                  "harmful_share": round(float(df["harmful"].mean()), 3), "months": "2026-04..2026-09",
                  "verdict_not_worth_it": k, "verdict_think": int((df["decision"] == "think").sum()),
                  "not_in_backtest": "market price and goals (bank lines have no product title; dataset has no goals)",
                  "overspend_definition": f"category month total > {1 + OVER_MARGIN:.2f} x usual level"},
        "same_number_of_warnings": {
            "rule_50_30_20": evaluate(df, "flag_503020", outcomes),
            "proportion": evaluate(df, "flag_proportion", outcomes),
            "overspend_model_only": evaluate(df, "flag_risk_only", outcomes),
            "verdict": evaluate(df, "flag_verdict", outcomes),
        },
        "verdict_reasons": {"high_risk": int(df["high_risk"].sum()), "above_usual_price": int(df["above_usual"].sum()),
                            "both": int((df["high_risk"] & df["above_usual"]).sum())},
    }
    for name, r in results["same_number_of_warnings"].items():
        print(f"{name:>22}: postponed {r['postponed_purchases']} ({r['postponed_share']:.0%}), precision {r['precision']:.2f}, "
              f"recall {r['recall']:.2f}, avoided ${r['avoided_per_family_month_usd']:.0f}/family-month, false alarms {r['false_alarms']}")
    print(results["verdict_reasons"])
    cols = ["customer_id", "transaction_date", "label", "price", "description", "risk", "budget", "total"]
    results["error_examples"] = {
        "not_worth_it_but_fine": json.loads(df[df["flag_verdict"] & ~df["harmful"]].nlargest(3, "price")[cols]
                                            .to_json(orient="records", date_format="iso")),
        "buy_but_harmful": json.loads(df[(df["decision"] == "buy") & df["harmful"]].nlargest(3, "price")[cols]
                                      .to_json(orient="records", date_format="iso")),
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "backtest_verdict.json").write_text(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
