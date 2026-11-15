"""Export the ML models and the demo family to JSON so they run inside the Chrome extension.

- Categorizer and price model are retrained in a compact size (fewer TF-IDF features)
  and re-evaluated on the same test data, so the extension's numbers are honest.
- Gradient-boosting models (overspend, recurring) are exported tree by tree.
- Test vectors let the JavaScript port be checked against Python.

Run from the project root:
    .venv/bin/python ml/export_extension.py
"""
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import f1_score
from sklearn.pipeline import FeatureUnion, Pipeline

sys.path.insert(0, str(Path(__file__).parent))
from categories import CATEGORIES, NEEDS, WANTS  # noqa: E402
from intents import INTENTS, TEST_QUESTIONS, training_phrases  # noqa: E402
from overspend_features import FEATURES  # noqa: E402
from recurring import SERIES_FEATURES  # noqa: E402
from text_utils import normalize  # noqa: E402

OUT = Path("extension/models")
DATA_OUT = Path("extension/data")
PROCESSED = Path("data/processed")
ROUND = 5


def r(x):
    return [round(float(v), ROUND) for v in x]


# ------------------------------------------------------------------ text models

def compact_text_model(max_char: int, max_word: int, clf, char_range=(2, 5), preprocessor=normalize):
    features = FeatureUnion([
        ("chars", TfidfVectorizer(preprocessor=preprocessor, analyzer="char_wb", ngram_range=char_range, min_df=2,
                                  sublinear_tf=True, max_features=max_char)),
        ("words", TfidfVectorizer(preprocessor=preprocessor, analyzer="word", ngram_range=(1, 2), min_df=2,
                                  sublinear_tf=True, max_features=max_word)),
    ])
    return Pipeline([("features", features), ("clf", clf)])


def export_union(pipe) -> list:
    parts = []
    for name, vec in pipe.named_steps["features"].transformer_list:
        vocab = sorted(vec.vocabulary_.items(), key=lambda kv: kv[1])
        parts.append({"analyzer": vec.analyzer, "ngram_range": list(vec.ngram_range),
                      "terms": [t for t, _ in vocab], "idf": r(vec.idf_)})
    return parts


def categorizer() -> dict:
    train = pd.read_parquet(PROCESSED / "descriptions_train.parquet")
    tx = pd.read_parquet(PROCESSED / "household_tx.parquet")
    test = tx[tx["label"].notna()]
    fams = np.sort(test["customer_id"].unique())
    pool = set(np.random.default_rng(42).choice(fams, size=len(fams) // 2, replace=False))
    test = test[~test["customer_id"].isin(pool)]  # same 50 held-out families as ml/train_categorizer.py
    model = compact_text_model(20000, 8000, LogisticRegression(C=5.0, max_iter=2000)).fit(train["text"], train["label"])
    f1 = f1_score(test["label"], model.predict(test["text"]), labels=CATEGORIES, average="macro", zero_division=0)
    clf = model.named_steps["clf"]
    sample = test.sample(40, random_state=0)
    return {"name": "categorizer", "test_macro_f1": round(f1, 4), "classes": list(clf.classes_),
            "features": export_union(model), "coef": [r(row) for row in clf.coef_], "intercept": r(clf.intercept_),
            "needs": sorted(NEEDS), "wants": sorted(WANTS),
            "tests": [{"text": t, "expected": p} for t, p in zip(sample["text"], model.predict(sample["text"]))]}


def price() -> dict:
    from train_price import clean_title, load, range_metrics, split
    df = load()
    train, val, test = split(df)
    model = compact_text_model(20000, 20000, Ridge(alpha=1.0), char_range=(3, 5), preprocessor=None)
    model.fit(train["text"], np.log(train["price"]))
    val_err = np.log(val["price"].to_numpy()) - model.predict(val["text"])
    overall = (float(np.quantile(val_err, 0.25)), float(np.quantile(val_err, 0.75)))
    mid = model.predict(test["text"])
    m = range_metrics(test["price"], np.exp(mid + overall[0]), np.exp(mid + overall[1]), np.exp(mid))
    old = joblib.load("ml/models/price.joblib")
    reg = model.named_steps["clf"]
    sample = test.sample(20, random_state=0)
    return {"name": "price", "test": m, "band": overall, "blend_weight": float(old.get("blend_weight", 0.05)),
            "hybrid_band": list(old.get("hybrid_band", overall)),
            "features": export_union(model), "coef": r(reg.coef_), "intercept": round(float(reg.intercept_), ROUND),
            "lowercase_text": True,
            "tests": [{"text": t, "expected": round(float(np.exp(p)), 2)} for t, p in
                      zip(sample["text"], model.predict(sample["text"]))],
            "_clean": "category | lowercased title with single spaces"}


def intent() -> dict:
    texts, labels = zip(*training_phrases())
    model = compact_text_model(20000, 5000, LogisticRegression(C=10.0, max_iter=2000), char_range=(2, 4),
                               preprocessor=None)
    model.fit(texts, labels)
    tt, tl = zip(*TEST_QUESTIONS)
    f1 = f1_score(tl, model.predict(tt), labels=INTENTS, average="macro", zero_division=0)
    clf = model.named_steps["clf"]
    return {"name": "intent", "test_macro_f1": round(f1, 4), "classes": list(clf.classes_),
            "features": export_union(model), "coef": [r(row) for row in clf.coef_], "intercept": r(clf.intercept_),
            "tests": [{"text": t, "expected": p} for t, p in zip(tt[:15], model.predict(tt[:15]))]}


# ------------------------------------------------------------------ tree models

def export_hgb(model, feature_names: list) -> dict:
    """HistGradientBoosting binary classifier: trees in the model's internal column order."""
    pre = model._preprocessor
    cat_mask = list(model.is_categorical_) if model.is_categorical_ is not None else [False] * len(feature_names)
    order = [f for f, c in zip(feature_names, cat_mask) if c] + [f for f, c in zip(feature_names, cat_mask) if not c]
    cat_values = {}
    if pre is not None and any(cat_mask):
        enc = pre.named_transformers_["encoder"]
        for f, cats in zip([f for f, c in zip(feature_names, cat_mask) if c], enc.categories_):
            cat_values[f] = [float(v) for v in cats]   # raw value -> its index is the encoded value
    trees = []
    for (p,) in model._predictors:
        n = p.nodes
        trees.append({
            "value": r(n["value"]), "feature": n["feature_idx"].tolist(), "threshold": r(n["num_threshold"]),
            "missing_left": n["missing_go_to_left"].tolist(), "left": n["left"].tolist(), "right": n["right"].tolist(),
            "leaf": n["is_leaf"].tolist(), "categorical": n["is_categorical"].tolist(), "bitset": n["bitset_idx"].tolist(),
            "cat_bitsets": p.raw_left_cat_bitsets.astype(np.int64).tolist() if p.raw_left_cat_bitsets.size else [],
        })
    return {"order": order, "categorical_values": cat_values,
            "baseline": float(np.ravel(model._baseline_prediction)[0]), "trees": trees}


def overspend() -> dict:
    b = joblib.load("ml/models/overspend.joblib")
    out = export_hgb(b["model"], b["features"])
    ex = pd.read_parquet(PROCESSED / "overspend_examples.parquet").sample(40, random_state=0)
    prob = b["model"].predict_proba(ex[b["features"]])[:, 1]
    out.update({"name": "overspend", "features": b["features"], "threshold": float(b["threshold"]), "red": 0.75,
                "tests": [{"x": r(row), "expected": round(float(p), 6)} for row, p in zip(ex[b["features"]].to_numpy(), prob)]})
    return out


def recurring() -> dict:
    b = joblib.load("ml/models/recurring.joblib")
    out = export_hgb(b["model"], b["features"])
    from recurring import build_series
    tx = pd.read_parquet(PROCESSED / "household_tx.parquet").rename(columns={"transaction_date": "date"})
    s = build_series(tx[tx["customer_id"].isin(["C000369", "C000009"])]).sample(30, random_state=0)
    prob = b["model"].predict_proba(s[b["features"]])[:, 1]
    out.update({"name": "recurring", "features": b["features"],
                "tests": [{"x": r(row), "expected": round(float(p), 6)} for row, p in zip(s[b["features"]].to_numpy(), prob)]})
    return out


# ------------------------------------------------------------------ demo family

def demo_family() -> dict:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from backend import demo
    tx = pd.read_parquet(PROCESSED / "household_tx.parquet")
    fam = tx[(tx["customer_id"] == demo.DEMO_CUSTOMER) & ~tx["is_fraud"]]
    bank = [{"id": f"demo-{r_.transaction_id}", "date": str(r_.transaction_date.date()), "amount": float(r_.amount),
             "description": r_.description, "merchant": r_.merchant_name, "member": "alex", "source": "bank"}
            for r_ in fam.itertuples()]
    end = pd.Timestamp("2026-09-30")  # last day of the dataset
    teens = []
    for key in ("maya", "leo"):
        for t in demo.teen_transactions(key, end):
            t.update(member=key, source="allowance" if t["description"].startswith("ALLOWANCE") else "bank")
            teens.append(t)
    c = pd.read_parquet(PROCESSED / "customers.parquet").set_index("customer_id").loc[demo.DEMO_CUSTOMER]
    return {
        "dataset_end": "2026-09-30", "anchor_month": demo.DEMO_ANCHOR_MONTH, "family_name": demo.ROOM_NAME,
        "household_income": float(c["household_income"]),
        "members": [{"key": p["key"], "name": p["name"].split()[0], "role": p["role"],
                     "allowance": p.get("allowance")} for p in demo.FAMILY],
        "pins": {"alex": "1111", "sam": "2222", "maya": "3333", "leo": "4444"},
        "family_goals": demo.FAMILY_GOALS, "personal_goals": demo.PERSONAL_GOALS,
        "plans": demo.PLANS, "seed_corrections": demo.SEED_CORRECTIONS,
        "transactions": bank + teens,
        "source": "Misata US Bank and Card Transactions (CC BY 4.0) + generated teen spending",
    }


def write(name: str, obj: dict, folder: Path = OUT) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.json"
    path.write_text(json.dumps(obj, separators=(",", ":")))
    print(f"{path}: {path.stat().st_size / 1e6:.1f} MB")


def main() -> None:
    cat = categorizer()
    print(f"compact categorizer: test macro-F1 {cat['test_macro_f1']}")
    write("categorizer", cat)
    pr = price()
    print(f"compact price model: {pr['test']}")
    write("price", pr)
    it = intent()
    print(f"compact intent model: test macro-F1 {it['test_macro_f1']}")
    write("intent", it)
    write("overspend", overspend())
    write("recurring", recurring())
    write("demo_family", demo_family(), DATA_OUT)
    summary = {"categorizer_macro_f1": cat["test_macro_f1"], "price": pr["test"], "intent_macro_f1": it["test_macro_f1"]}
    Path("ml/results/extension_models.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
