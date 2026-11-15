"""ML part 2: find recurring payments and predict the next one.

Labels: the dataset marks every transaction that belongs to a recurring stream
(rent, salary, bills, subscriptions). A series is recurring when most of its
transactions carry such a mark.
Split: 70% of families for training, 30% for testing (never seen).
Detection uses history up to 2026-06-30; next-payment accuracy is checked on
the first real payment after that date.

Run from the project root:
    .venv/bin/python ml/train_recurring.py
"""
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import precision_recall_fscore_support

sys.path.insert(0, str(Path(__file__).parent))
from recurring import SERIES_FEATURES, add_keys, build_series, next_occurrence  # noqa: E402

PROCESSED = Path("data/processed")
MODELS = Path("ml/models")
RESULTS = Path("ml/results")
CUTOFF = pd.Timestamp("2026-06-30")
SEED = 42


def prf(y, p) -> dict:
    pr, rc, f, _ = precision_recall_fscore_support(y, p, average="binary", zero_division=0)
    return {"precision": round(pr, 3), "recall": round(rc, 3), "f1": round(f, 3)}


def main() -> None:
    tx = pd.read_parquet(PROCESSED / "household_tx.parquet")
    tx = tx[~tx["is_fraud"]].rename(columns={"transaction_date": "date"})
    families = np.sort(tx["customer_id"].unique())
    rng = np.random.default_rng(SEED)
    test_fams = set(rng.choice(families, size=int(len(families) * 0.3), replace=False))

    hist = tx[tx["date"] <= CUTOFF]
    series = build_series(hist)
    series["is_test"] = series["customer_id"].isin(test_fams)
    train, test = series[~series["is_test"]], series[series["is_test"]]
    print(f"Series: train {len(train):,} | test {len(test):,} | recurring share {series['label'].mean():.1%}")

    model = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, random_state=SEED)
    model.fit(train[SERIES_FEATURES], train["label"])
    pred = model.predict(test[SERIES_FEATURES])
    base = ((test["n"] >= 3) & (test["n_months"] >= 3)).astype(int)
    results = {"setup": {"history_until": str(CUTOFF.date()), "train_series": int(len(train)),
                         "test_series": int(len(test)), "test_families": len(test_fams)},
               "detection": {"baseline_3_times_3_months": prf(test["label"], base), "model": prf(test["label"], pred)}}

    # Next payment: for test series the model calls recurring, compare with the first real payment after cutoff.
    future = add_keys(tx[(tx["date"] > CUTOFF) & tx["customer_id"].isin(test_fams)])
    first_after = future.sort_values("date").groupby(["customer_id", "key", "is_inflow"]).first().reset_index()
    found = test[pred == 1].merge(first_after[["customer_id", "key", "is_inflow", "date", "amount"]],
                                  left_on=["customer_id", "key", "is_inflow"],
                                  right_on=["customer_id", "key", "is_inflow"], how="inner")
    found["is_inflow"] = found["is_inflow"].astype(bool)
    model_date = [next_occurrence(r.last_date, r.gap_median, CUTOFF) for r in found.itertuples()]
    base_date = [r.last_date + pd.Timedelta(days=30) if r.last_date + pd.Timedelta(days=30) > CUTOFF
                 else CUTOFF + pd.Timedelta(days=1) for r in found.itertuples()]
    actual = found["date"]
    d_model = np.abs((pd.Series(model_date) - actual.values).dt.days)
    d_base = np.abs((pd.Series(base_date) - actual.values).dt.days)
    a_model = np.abs(found["median_amount"] - found["amount"]) / found["amount"].abs()
    a_base = np.abs(found["last_amount"] - found["amount"]) / found["amount"].abs()
    results["next_payment"] = {
        "series_checked": int(len(found)),
        "baseline_last_plus_30_days": {"median_days_off": float(np.median(d_base)), "within_3_days": round(float(np.mean(d_base <= 3)), 3),
                                       "median_amount_error": round(float(np.median(a_base)), 3)},
        "model": {"median_days_off": float(np.median(d_model)), "within_3_days": round(float(np.mean(d_model <= 3)), 3),
                  "median_amount_error": round(float(np.median(a_model)), 3)},
    }
    print(json.dumps(results["detection"], indent=1))
    print(json.dumps(results["next_payment"], indent=1))

    test = test.assign(pred=pred, prob=model.predict_proba(test[SERIES_FEATURES])[:, 1])
    cols = ["key", "n", "gap_median", "median_amount", "prob"]
    results["error_examples"] = {
        "missed": test[(test["label"] == 1) & (test["pred"] == 0)].nsmallest(3, "prob")[cols].round(2).to_dict("records"),
        "false_alarm": test[(test["label"] == 0) & (test["pred"] == 1)].nlargest(3, "prob")[cols].round(2).to_dict("records"),
    }
    test[["key", "n", "n_months", "gap_median", "median_amount", "is_inflow", "label", "pred"]].sample(
        100, random_state=SEED).to_parquet(PROCESSED / "recurring_test_sample.parquet", index=False)

    MODELS.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "features": SERIES_FEATURES}, MODELS / "recurring.joblib")
    (RESULTS / "recurring.json").write_text(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
