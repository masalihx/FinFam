"""Step 3 of FinPilot: overspend forecast (ML 2).

Time split: train on months before 2026-01, pick the decision threshold on
2026-01..2026-03, report on 2026-04..2026-09 (never seen during training).

Run from the project root:
    .venv/bin/python ml/train_overspend.py
"""
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, brier_score_loss, precision_recall_fscore_support

sys.path.insert(0, str(Path(__file__).parent))
from overspend_features import CHECK_DAYS, FEATURES, MONOTONE, OVER_MARGIN, build_examples  # noqa: E402

PROCESSED = Path("data/processed")
MODELS = Path("ml/models")
RESULTS = Path("ml/results")
VAL_START = pd.Period("2026-01", "M")
TEST_START = pd.Period("2026-04", "M")
THRESHOLD = 1 + OVER_MARGIN


def make_model() -> HistGradientBoostingClassifier:
    monotone = [MONOTONE.get(f, 0) for f in FEATURES]
    categorical = [f == "category_code" for f in FEATURES]
    return HistGradientBoostingClassifier(
        max_iter=400, learning_rate=0.05, max_leaf_nodes=31, l2_regularization=1.0,
        monotonic_cst=monotone, categorical_features=categorical, random_state=42)


def scores(y, decision, score) -> dict:
    p, r, f, _ = precision_recall_fscore_support(y, decision, average="binary", zero_division=0)
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3),
            "pr_auc": round(average_precision_score(y, score), 3)}


def best_threshold(y, prob) -> float:
    """Threshold with the best F1 on validation months."""
    grid = np.linspace(0.1, 0.9, 81)
    f1s = [precision_recall_fscore_support(y, prob >= t, average="binary", zero_division=0)[2] for t in grid]
    return float(grid[int(np.argmax(f1s))])


def baseline_scores(df: pd.DataFrame) -> dict:
    """Two simple ways to guess the month end without ML."""
    proportion = df["proportion_ratio"]                        # spent so far x days_in_month / day
    pace = df["spent_ratio"] + df["hist_after_day_ratio"]      # spent so far + what usually comes later
    return {"proportion": proportion, "pace": pace}


def main() -> None:
    MODELS.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    tx = pd.read_parquet(PROCESSED / "household_tx.parquet")
    customers = pd.read_parquet(PROCESSED / "customers.parquet")

    ex = build_examples(tx, customers)
    train = ex[ex["month"] < VAL_START]
    val = ex[(ex["month"] >= VAL_START) & (ex["month"] < TEST_START)]
    test = ex[ex["month"] >= TEST_START]
    print(f"Examples: train {len(train):,} | val {len(val):,} | test {len(test):,}; "
          f"overspend rate in test {test['is_over'].mean():.1%}")

    model = make_model().fit(train[FEATURES], train["is_over"])
    threshold = best_threshold(val["is_over"], model.predict_proba(val[FEATURES])[:, 1])

    # Final model: train + validation months, same threshold.
    trval = pd.concat([train, val])
    model = make_model().fit(trval[FEATURES], trval["is_over"])
    prob = model.predict_proba(test[FEATURES])[:, 1]
    y = test["is_over"].to_numpy()

    results = {
        "setup": {"train_months": f"{ex['month'].min()}..{VAL_START - 1}",
                  "val_months": f"{VAL_START}..{TEST_START - 1}",
                  "test_months": f"{TEST_START}..{ex['month'].max()}",
                  "test_examples": int(len(test)), "overspend_rate_test": round(float(y.mean()), 3),
                  "overspend_definition": f"month-end spend > {THRESHOLD:.2f} x median of previous 6 months",
                  "check_days": CHECK_DAYS, "model_threshold": round(threshold, 2)},
        "test": {},
    }
    base = baseline_scores(test)
    results["test"]["baseline_proportion"] = scores(y, base["proportion"] > THRESHOLD, base["proportion"])
    results["test"]["baseline_pace"] = scores(y, base["pace"] > THRESHOLD, base["pace"])
    results["test"]["model"] = scores(y, prob >= threshold, prob)
    results["test"]["model"]["brier"] = round(brier_score_loss(y, prob), 4)

    for name, r in results["test"].items():
        print(f"{name:>20}: " + ", ".join(f"{k}={v}" for k, v in r.items()))

    by_day = {}
    for d in CHECK_DAYS:
        m = (test["day"] == d).to_numpy()
        by_day[d] = {"proportion": scores(y[m], base["proportion"][m] > THRESHOLD, base["proportion"][m]),
                     "model": scores(y[m], prob[m] >= threshold, prob[m])}
    results["by_day"] = by_day
    print("By check day (recall / precision):")
    for d, r in by_day.items():
        print(f"  day {d:>2}: proportion {r['proportion']['recall']:.2f}/{r['proportion']['precision']:.2f}"
              f" | model {r['model']['recall']:.2f}/{r['model']['precision']:.2f}")

    # Calibration: when the model says ~70%, does overspend happen ~70% of the time?
    bins = np.linspace(0, 1, 11)
    idx = np.clip(np.digitize(prob, bins) - 1, 0, 9)
    results["calibration"] = [
        {"bin": f"{bins[i]:.1f}-{bins[i + 1]:.1f}", "n": int((idx == i).sum()),
         "predicted": round(float(prob[idx == i].mean()), 3), "actual": round(float(y[idx == i].mean()), 3)}
        for i in range(10) if (idx == i).sum() > 0
    ]

    # Error examples: confident misses and false alarms.
    test = test.assign(prob=prob)
    cols = ["customer_id", "label", "month", "day", "spent_to_date", "budget", "total", "prob"]
    misses = test[(test["is_over"] == 1)].nsmallest(3, "prob")[cols]
    alarms = test[(test["is_over"] == 0)].nlargest(3, "prob")[cols]
    results["error_examples"] = {
        "missed_overspend": json.loads(misses.astype({"month": str}).round(2).to_json(orient="records")),
        "false_alarm": json.loads(alarms.astype({"month": str}).round(2).to_json(orient="records")),
    }

    joblib.dump({"model": model, "threshold": threshold, "features": FEATURES}, MODELS / "overspend.joblib")
    ex.to_parquet(PROCESSED / "overspend_examples.parquet", index=False)
    (RESULTS / "overspend.json").write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    print(f"Saved model and results ({RESULTS / 'overspend.json'})")


if __name__ == "__main__":
    main()
