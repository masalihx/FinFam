"""Gemini as a baseline for the recurring-payment and categorization models.

Same test items as our models; one request per 100 items.
Run from the project root (needs GEMINI_API_KEY in .env):
    .venv/bin/python ml/gemini_baselines.py
"""
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import requests
from sklearn.metrics import f1_score, precision_recall_fscore_support

sys.path.insert(0, str(Path(__file__).parent))
from categories import CATEGORIES  # noqa: E402
from price_hybrid import GEMINI_MODEL, gemini_key  # noqa: E402

PROCESSED = Path("data/processed")
RESULTS = Path("ml/results")


def ask(prompt: str):
    resp = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        headers={"x-goog-api-key": gemini_key(), "Content-Type": "application/json"},
        json={"contents": [{"parts": [{"text": prompt}]}],
              "generationConfig": {"responseMimeType": "application/json", "temperature": 0}},
        timeout=300)
    resp.raise_for_status()
    return json.loads(resp.json()["candidates"][0]["content"]["parts"][-1]["text"])


def recurring() -> dict:
    s = pd.read_parquet(PROCESSED / "recurring_test_sample.parquet")
    items = "\n".join(
        f"{i + 1}. merchant='{r.key}', payments={r.n} over {r.n_months} months, usual gap {r.gap_median:.0f} days, "
        f"usual amount ${abs(r.median_amount):.2f}, {'money in' if r.is_inflow else 'money out'}"
        for i, r in enumerate(s.itertuples()))
    prompt = ("For each series of bank transactions below, answer 1 if it is a regular recurring payment "
              "(salary, rent, bill, subscription, loan, insurance) and 0 otherwise. "
              "Answer only with a JSON array of 0/1, one per series, same order.\n\n" + items)
    g = np.array(ask(prompt), dtype=int)[:len(s)]
    bundle = joblib.load("ml/models/recurring.joblib")
    full = pd.read_parquet(PROCESSED / "household_tx.parquet")  # noqa: F841 (kept for clarity of source)
    p, r, f, _ = precision_recall_fscore_support(s["label"], g, average="binary", zero_division=0)
    return {"test_series": int(len(s)), "gemini": {"precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3)},
            "note": "Gemini sees a text summary of each series (count, gap, amount), not the raw dates.",
            "model_features_used": bundle["features"]}


def categorization() -> dict:
    tx = pd.read_parquet(PROCESSED / "household_tx.parquet")
    s = tx[tx["label"].notna()].sample(200, random_state=1)
    model = joblib.load("ml/models/categorizer.joblib")
    ours = model.predict(s["text"])
    items = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(s["text"]))
    prompt = (f"Classify each US bank transaction into exactly one category from this list: {', '.join(CATEGORIES)}. "
              "Answer only with a JSON array of category names, one per transaction, same order.\n\n" + items)
    g = [str(x) for x in ask(prompt)][:len(s)]
    y = s["label"].tolist()
    return {"test_transactions": int(len(s)),
            "our_model_macro_f1": round(f1_score(y, ours, labels=CATEGORIES, average="macro", zero_division=0), 3),
            "gemini_macro_f1": round(f1_score(y, g, labels=CATEGORIES, average="macro", zero_division=0), 3),
            "our_model_accuracy": round(float(np.mean(np.array(ours) == np.array(y))), 3),
            "gemini_accuracy": round(float(np.mean(np.array(g) == np.array(y))), 3)}


def main() -> None:
    out = {"gemini_model": GEMINI_MODEL}
    out["recurring"] = recurring()
    print("recurring:", out["recurring"]["gemini"])
    out["categorization"] = categorization()
    print("categorization:", out["categorization"])
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "gemini_baselines.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
