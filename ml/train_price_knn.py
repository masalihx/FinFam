"""Market price from the database: median price of the most similar Amazon products (k nearest neighbours).

Same split as ml/train_price.py (by store, so variants of one product are never in both).
Compares with the category median and with the ridge model on the same unseen-store test set,
then exports a compact product index for the Chrome extension.

    .venv/bin/python ml/train_price_knn.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

sys.path.insert(0, str(Path(__file__).parent))
from train_price import load, range_metrics, split  # noqa: E402

OUT = Path("extension/models/price_index.json")
RESULTS = Path("ml/results/price_knn.json")
TOKEN = r"(?u)[^\W_]{2,}|\d+"  # same tokens as the JS port: words of 2+ letters, numbers


def title_text(df: pd.DataFrame) -> pd.Series:
    return df["title"].str.lower().str.replace(r"\s+", " ", regex=True).str.slice(0, 120)


def knn_prices(vec, X_train, prices, texts, k):
    """Similarity-weighted median of the k most similar training products, and their 25-75% range."""
    Q = vec.transform(texts)
    S = (Q @ X_train.T).tocsr()
    mid, lo, hi, sim = [], [], [], []
    for i in range(S.shape[0]):
        row = S.getrow(i)
        if row.nnz == 0:
            mid.append(np.nan); lo.append(np.nan); hi.append(np.nan); sim.append(0.0)  # noqa: E702
            continue
        top = row.indices[np.argsort(-row.data)[:k]]
        w = np.sort(row.data)[::-1][:k]
        p = prices[top]
        order = np.argsort(p)
        cw = np.cumsum(w[order]) / w.sum()
        mid.append(float(p[order][np.searchsorted(cw, 0.5)]))
        lo.append(float(p[order][np.searchsorted(cw, 0.25)]))
        hi.append(float(p[order][min(len(p) - 1, np.searchsorted(cw, 0.75))]))
        sim.append(float(w[0]))
    return np.array(mid), np.array(lo), np.array(hi), np.array(sim)


def main() -> None:
    df = load()
    train, val, test = split(df)
    results = {"setup": {"train": int(len(train)), "test": int(len(test)), "split": "by store", "prices_as_of": 2023}}
    cat_med = train.groupby("main_category")["price"].median()
    base = test["main_category"].map(cat_med).fillna(train["price"].median()).to_numpy()
    results["category_median"] = range_metrics(test["price"], base * 0.7, base * 1.4, base)

    best = None
    for max_features, k in [(30000, 10), (30000, 20), (60000, 20)]:
        vec = TfidfVectorizer(token_pattern=TOKEN, max_features=max_features, sublinear_tf=True, min_df=2)
        X = vec.fit_transform(title_text(train))
        mid, lo, hi, _ = knn_prices(vec, X, train["price"].to_numpy(), title_text(val), k)
        ok = ~np.isnan(mid)
        err = float(np.median(np.abs(mid[ok] - val["price"].to_numpy()[ok]) / val["price"].to_numpy()[ok]))
        print(f"validation: features={max_features} k={k} median error={err:.3f}")
        if best is None or err < best[0]:
            best = (err, max_features, k, vec, X)
    _, max_features, k, vec, X = best
    mid, lo, hi, sim = knn_prices(vec, X, train["price"].to_numpy(), title_text(test), k)
    mid = np.where(np.isnan(mid), base, mid)
    lo = np.where(np.isnan(lo), base * 0.7, lo)
    hi = np.where(np.isnan(hi), base * 1.4, hi)
    results["knn"] = range_metrics(test["price"], lo, hi, mid)
    results["knn"].update({"k": k, "max_features": max_features})
    ridge = json.loads(Path("ml/results/price.json").read_text())["model"]
    results["ridge_full_model"] = ridge
    for name in ("category_median", "knn"):
        print(name, results[name])
    print("ridge", ridge)

    # Export: titles (for display), prices, vocabulary and idf; the JS builds the inverted index on load.
    terms = sorted(vec.vocabulary_, key=vec.vocabulary_.get)
    examples = test.sample(15, random_state=3)
    m2, _, _, _ = knn_prices(vec, X, train["price"].to_numpy(), title_text(examples), k)
    index = {"k": k, "token_pattern": "[^\\W_]{2,}|\\d+", "terms": terms, "idf": [round(float(v), 4) for v in vec.idf_],
             "titles": title_text(train).tolist(), "prices": train["price"].round(2).tolist(),
             "tests": [{"title": t, "expected": round(float(p), 2)} for t, p in zip(examples["title"], m2)]}
    OUT.write_text(json.dumps(index, separators=(",", ":")))
    print(f"{OUT}: {OUT.stat().st_size / 1e6:.1f} MB, {len(index['titles'])} products")
    RESULTS.write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
