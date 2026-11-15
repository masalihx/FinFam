"""Step 2 of FinPilot: transaction categorization (ML 1).

Train on one synthetic dataset (DoDataThings), test on another one built by
different people (misata family transactions). Compare with two baselines and
measure how fast the model improves from a family's own corrections.

Run from the project root:
    .venv/bin/python ml/train_categorizer.py
"""
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, f1_score
from sklearn.pipeline import FeatureUnion, Pipeline

sys.path.insert(0, str(Path(__file__).parent))
import keyword_baseline  # noqa: E402
from categories import CATEGORIES  # noqa: E402
from text_utils import normalize  # noqa: E402

PROCESSED = Path("data/processed")
MODELS = Path("ml/models")
RESULTS = Path("ml/results")
SEED = 42
CORRECTION_STEPS = [0, 10, 50, 200]
CORRECTION_WEIGHT = 5.0  # a family's own correction counts more than a generic example


def make_model() -> Pipeline:
    features = FeatureUnion([
        ("chars", TfidfVectorizer(preprocessor=normalize, analyzer="char_wb", ngram_range=(2, 5),
                                  min_df=2, sublinear_tf=True)),
        ("words", TfidfVectorizer(preprocessor=normalize, analyzer="word", ngram_range=(1, 2),
                                  min_df=2, sublinear_tf=True)),
    ])
    clf = LogisticRegression(C=5.0, max_iter=2000)
    return Pipeline([("features", features), ("clf", clf)])


def macro_f1(y_true, y_pred) -> float:
    return f1_score(y_true, y_pred, labels=CATEGORIES, average="macro", zero_division=0)


def split_families(test: pd.DataFrame):
    """Split families in two halves.

    Pool (dev) families: used to design the model and to supply user corrections.
    Holdout (test) families: touched only for the final numbers.
    """
    families = np.sort(test["customer_id"].unique())
    rng = np.random.default_rng(SEED)
    pool_ids = set(rng.choice(families, size=len(families) // 2, replace=False))
    is_pool = test["customer_id"].isin(pool_ids)
    return test[is_pool], test[~is_pool]


def corrections_curve(train: pd.DataFrame, pool: pd.DataFrame, holdout: pd.DataFrame) -> list:
    """Retrain after a user fixes k mistakes they saw in their own transactions.

    The pool is ordered by date, so corrections are the earliest mistakes a
    family would notice. The holdout families never contribute corrections.
    """
    base = make_model().fit(train["text"], train["label"])
    pool = pool.sort_values("transaction_date")
    pool_pred = base.predict(pool["text"])
    mistakes = pool[pool_pred != pool["label"].to_numpy()]
    # One correction per distinct merchant text pattern, like a user fixing a merchant once.
    mistakes = mistakes.assign(key=mistakes["text"].map(normalize)).drop_duplicates("key")

    curve = []
    for k in CORRECTION_STEPS:
        fixes = mistakes.head(k)
        texts = pd.concat([train["text"], fixes["text"]])
        labels = pd.concat([train["label"], fixes["label"]])
        weights = np.r_[np.ones(len(train)), np.full(len(fixes), CORRECTION_WEIGHT)]
        model = make_model().fit(texts, labels, clf__sample_weight=weights)
        score = macro_f1(holdout["label"], model.predict(holdout["text"]))
        curve.append({"corrections": int(len(fixes)), "macro_f1": round(score, 4)})
        print(f"  after {len(fixes):>3} corrections: macro-F1 = {score:.3f}")
    return curve


def main() -> None:
    MODELS.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)

    train = pd.read_parquet(PROCESSED / "descriptions_train.parquet")
    tx = pd.read_parquet(PROCESSED / "household_tx.parquet")
    labelled = tx[tx["label"].notna()].copy()
    pool, test = split_families(labelled)
    print(f"Train: {len(train):,} descriptions | Dev: {len(pool):,} | Test: {len(test):,} family transactions")

    model = make_model().fit(train["text"], train["label"])
    constant = train["label"].mode().iloc[0]  # all training categories are equally common

    results = {"setup": {"train": "DoDataThings v2 (68k synthetic descriptions)",
                         "test": "misata family transactions, holdout half of the families",
                         "dev_transactions": int(len(pool)), "test_transactions": int(len(test))}}
    for split_name, part in [("dev", pool), ("test", test)]:
        kw_pred = keyword_baseline.predict(part["text"])
        pred = model.predict(part["text"])
        results[split_name] = {
            "constant_baseline": round(macro_f1(part["label"], [constant] * len(part)), 4),
            "keyword_baseline": round(macro_f1(part["label"], kw_pred), 4),
            "model": round(macro_f1(part["label"], pred), 4),
        }
        print(f"{split_name}: " + ", ".join(f"{k} = {v:.3f}" for k, v in results[split_name].items()))

    # Per-category scores and error examples come from the test families.
    pred = model.predict(test["text"])
    kw_pred = keyword_baseline.predict(test["text"])
    report = classification_report(test["label"], pred, labels=CATEGORIES, zero_division=0, output_dict=True)
    results["model_per_category_f1"] = {c: round(report[c]["f1-score"], 3) for c in CATEGORIES}
    kw_report = classification_report(test["label"], kw_pred, labels=CATEGORIES, zero_division=0, output_dict=True)
    results["keyword_per_category_f1"] = {c: round(kw_report[c]["f1-score"], 3) for c in CATEGORIES}

    errors = test.assign(pred=pred)[pred != test["label"].to_numpy()]
    errors = errors.assign(pair=errors["label"] + " -> " + errors["pred"])
    top_pairs = errors["pair"].value_counts().head(8)
    results["top_confusions"] = top_pairs.to_dict()
    results["error_examples"] = [
        {"text": row.text, "true": row.label, "predicted": row.pred}
        for pair in top_pairs.index[:5]
        for row in errors[errors["pair"] == pair].head(2).itertuples()
    ]

    print("Learning from corrections:")
    results["corrections_curve"] = corrections_curve(train, pool, test)
    results["corrections_setup"] = {"pool_families": int(pool["customer_id"].nunique()),
                                    "holdout_families": int(test["customer_id"].nunique()),
                                    "correction_weight": CORRECTION_WEIGHT}

    joblib.dump(model, MODELS / "categorizer.joblib")
    (RESULTS / "categorizer.json").write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"Saved model to {MODELS / 'categorizer.joblib'} and results to {RESULTS / 'categorizer.json'}")


if __name__ == "__main__":
    main()
