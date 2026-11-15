"""ML part 4b: hybrid market price = our model + Gemini.

The blend weight and the range width are chosen on validation products;
the final numbers come from the same 100 test products used for every method.

Run from the project root (needs GEMINI_API_KEY in .env):
    .venv/bin/python ml/price_hybrid.py
"""
import json
import os
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent))
from train_price import clean_title, load, split  # noqa: E402

GEMINI_MODEL = "gemini-3.5-flash"
RESULTS = Path("ml/results")
MODELS = Path("ml/models")


def gemini_key() -> str:
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"]
    env = dict(line.split("=", 1) for line in Path(".env").read_text().splitlines() if "=" in line)
    return env["GEMINI_API_KEY"].strip()


def gemini_prices(df: pd.DataFrame, batch: int = 100) -> np.ndarray:
    """Gemini's price estimate for each product, 100 products per request."""
    out = []
    for start in range(0, len(df), batch):
        part = df.iloc[start:start + batch]
        items = "\n".join(f"{i + 1}. [{r.main_category}] {str(r.title)[:150]}" for i, r in enumerate(part.itertuples()))
        prompt = ("Estimate the typical US Amazon price in 2023 (USD) for each product below. "
                  "Answer only with a JSON array of numbers, one per product, in the same order.\n\n" + items)
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
            headers={"x-goog-api-key": gemini_key(), "Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"responseMimeType": "application/json", "temperature": 0}},
            timeout=300)
        resp.raise_for_status()
        values = json.loads(resp.json()["candidates"][0]["content"]["parts"][-1]["text"])
        if len(values) != len(part):
            raise ValueError(f"Gemini returned {len(values)} prices for {len(part)} products")
        out.extend(float(v) for v in values)
    return np.clip(np.array(out), 0.5, None)


def metrics(price, point, low=None, high=None) -> dict:
    ape = np.abs(point - price) / price
    m = {"median_abs_pct_error": round(float(np.median(ape)), 3), "within_25pct": round(float(np.mean(ape <= 0.25)), 3)}
    if low is not None:
        m["range_coverage"] = round(float(np.mean((price >= low) & (price <= high))), 3)
        m["median_range_width_ratio"] = round(float(np.median(high / low)), 2)
    return m


def main() -> None:
    bundle = joblib.load(MODELS / "price.joblib")
    model = bundle["model"]
    df = load()
    _, val, test_full = split(df)
    val_s = val.sample(200, random_state=7)
    test_s = pd.read_parquet("data/processed/price_test_sample.parquet")

    def ours(d):
        return np.exp(model.predict(d["main_category"].fillna("") + " | " + d["title"].map(clean_title)))

    # Validation: choose blend weight w (log space) and the middle-50% band of the blend.
    v_ours, v_gem, v_price = ours(val_s), gemini_prices(val_s), val_s["price"].to_numpy()
    weights = np.linspace(0, 1, 21)
    errs = [np.median(np.abs(np.exp(w * np.log(v_ours) + (1 - w) * np.log(v_gem)) - v_price) / v_price) for w in weights]
    w = float(weights[int(np.argmin(errs))])
    v_blend = np.exp(w * np.log(v_ours) + (1 - w) * np.log(v_gem))
    resid = np.log(v_price) - np.log(v_blend)
    band = (float(np.quantile(resid, 0.25)), float(np.quantile(resid, 0.75)))
    print(f"Validation: best weight for our model = {w:.2f}; band {band}")

    # Test.
    t_ours, t_gem, t_price = ours(test_s), gemini_prices(test_s), test_s["price"].to_numpy()
    t_blend = np.exp(w * np.log(t_ours) + (1 - w) * np.log(t_gem))
    cat_med = df.groupby("main_category")["price"].median()
    t_base = test_s["main_category"].map(cat_med).fillna(df["price"].median()).to_numpy()
    results = {
        "setup": {"gemini_model": GEMINI_MODEL, "validation_products": 200, "test_products": int(len(test_s)),
                  "blend_weight_our_model": w, "band_log": band},
        "test": {
            "baseline_category_median": metrics(t_price, t_base),
            "our_model": metrics(t_price, t_ours),
            "gemini": metrics(t_price, t_gem),
            "hybrid": metrics(t_price, t_blend, t_blend * np.exp(band[0]), t_blend * np.exp(band[1])),
        },
    }
    for k, v in results["test"].items():
        print(f"{k:>25}: {v}")
    joblib.dump({**bundle, "blend_weight": w, "hybrid_band": band, "gemini_model": GEMINI_MODEL}, MODELS / "price.joblib")
    (RESULTS / "price_hybrid.json").write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
