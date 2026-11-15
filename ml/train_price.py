"""ML part 4: market price range of a product from its title.

Data: Amazon Products 2023 (milistu/AMAZON-Products-2023, MIT), prices as of 2023.
Model: ridge regression on TF-IDF of the title (+ category) predicts log price.
Range "similar items cost $A-B" = prediction x the middle 50% of validation errors.
Split by store/brand, so variants of one product never sit in both train and test.

Run from the project root:
    .venv/bin/python ml/train_price.py
"""
import json
import re
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import FeatureUnion, Pipeline

RAW = Path("data/raw/amazon_products_2023.parquet")
MODELS = Path("ml/models")
RESULTS = Path("ml/results")
SEED = 42
MIN_PRICE, MAX_PRICE = 1.0, 5000.0


def clean_title(t: str) -> str:
    return re.sub(r"\s+", " ", str(t)).strip().lower()


def load() -> pd.DataFrame:
    df = pd.read_parquet(RAW)
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df = df[df["price"].between(MIN_PRICE, MAX_PRICE) & df["title"].notna()].copy()
    df["text"] = df["main_category"].fillna("") + " | " + df["title"].map(clean_title)
    df["store_key"] = df["store"].fillna("").str.lower().str.strip().replace("", np.nan)
    df["store_key"] = df["store_key"].fillna(df["parent_asin"])  # unknown store: its own group
    return df.drop_duplicates("text").reset_index(drop=True)


def make_model() -> Pipeline:
    features = FeatureUnion([
        ("words", TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=200_000, sublinear_tf=True)),
        ("chars", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=3, max_features=200_000,
                                  sublinear_tf=True)),
    ])
    return Pipeline([("features", features), ("ridge", Ridge(alpha=1.0))])


def split(df: pd.DataFrame):
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED)
    train_idx, rest_idx = next(gss.split(df, groups=df["store_key"]))
    rest = df.iloc[rest_idx]
    gss2 = GroupShuffleSplit(n_splits=1, test_size=0.5, random_state=SEED)
    val_idx, test_idx = next(gss2.split(rest, groups=rest["store_key"]))
    return df.iloc[train_idx], rest.iloc[val_idx], rest.iloc[test_idx]


def range_metrics(price, low, high, point) -> dict:
    price, low, high, point = map(np.asarray, (price, low, high, point))
    ape = np.abs(point - price) / price
    return {
        "median_abs_pct_error": round(float(np.median(ape)), 3),
        "within_25pct": round(float(np.mean(ape <= 0.25)), 3),
        "range_coverage": round(float(np.mean((price >= low) & (price <= high))), 3),
        "median_range_width_ratio": round(float(np.median(high / low)), 2),
    }


def main() -> None:
    df = load()
    train, val, test = split(df)
    print(f"Products: {len(df):,} | train {len(train):,} | val {len(val):,} | test {len(test):,} (split by store)")

    model = make_model().fit(train["text"], np.log(train["price"]))

    # Middle-50% error band from validation, per category (fallback: overall).
    val_err = np.log(val["price"].to_numpy()) - model.predict(val["text"])
    band = pd.DataFrame({"cat": val["main_category"].to_numpy(), "err": val_err})
    overall = (float(np.quantile(val_err, 0.25)), float(np.quantile(val_err, 0.75)))
    per_cat = {c: (float(g["err"].quantile(0.25)), float(g["err"].quantile(0.75)))
               for c, g in band.groupby("cat") if len(g) >= 50}

    def predict_range(texts, cats):
        mid = model.predict(texts)
        lo_q = np.array([per_cat.get(c, overall)[0] for c in cats])
        hi_q = np.array([per_cat.get(c, overall)[1] for c in cats])
        return np.exp(mid + lo_q), np.exp(mid + hi_q), np.exp(mid)

    low, high, point = predict_range(test["text"], test["main_category"])
    results = {"setup": {"products": int(len(df)), "train": int(len(train)), "val": int(len(val)),
                         "test": int(len(test)), "split": "by store/brand", "prices_as_of": 2023}}
    results["model"] = range_metrics(test["price"], low, high, point)

    # Baseline: price range of the product's category in the training data.
    cat_q = train.groupby("main_category")["price"].quantile([0.25, 0.5, 0.75]).unstack()
    all_q = train["price"].quantile([0.25, 0.5, 0.75])
    q = test["main_category"].map(lambda c: cat_q.loc[c] if c in cat_q.index else all_q)
    q = pd.DataFrame(list(q), index=test.index)
    results["baseline_category"] = range_metrics(test["price"], q[0.25], q[0.75], q[0.5])

    for name in ("baseline_category", "model"):
        r = results[name]
        print(f"{name:>18}: median error {r['median_abs_pct_error']:.0%}, within ±25%: {r['within_25pct']:.0%}, "
              f"range covers price: {r['range_coverage']:.0%}, range width x{r['median_range_width_ratio']}")

    # Error examples for the write-up.
    t = test.assign(low=low, high=high, point=point, ratio=point / test["price"])
    results["error_examples"] = {
        "too_low": t.nsmallest(3, "ratio")[["title", "main_category", "price", "point"]].round(2).to_dict("records"),
        "too_high": t.nlargest(3, "ratio")[["title", "main_category", "price", "point"]].round(2).to_dict("records"),
    }
    # Sample kept for the Gemini comparison (same products for every method).
    test.sample(100, random_state=SEED)[["title", "main_category", "price"]].to_parquet(
        "data/processed/price_test_sample.parquet", index=False)

    MODELS.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "per_cat": per_cat, "overall": overall}, MODELS / "price.joblib")
    (RESULTS / "price.json").write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    for title in ["Sony WH-1000XM5 Wireless Noise Canceling Headphones", "Kids winter jacket waterproof",
                  "Stainless steel water bottle 32 oz", "Gaming laptop 16GB RAM RTX 4060"]:
        lo, hi, pt = predict_range([f"All Electronics | {clean_title(title)}"], ["All Electronics"])
        print(f"  {title}: ${lo[0]:.0f}-{hi[0]:.0f} (typical ${pt[0]:.0f})")


if __name__ == "__main__":
    main()
