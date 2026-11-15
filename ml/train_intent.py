"""Step 8 of FinPilot: intent classifier for the assistant (ML 4).

Run from the project root:
    .venv/bin/python ml/train_intent.py
"""
import json
import sys
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.pipeline import FeatureUnion, Pipeline

sys.path.insert(0, str(Path(__file__).parent))
from intents import FRESH_TEST_QUESTIONS, INTENTS, TEST_QUESTIONS, keyword_intent, training_phrases  # noqa: E402

MODELS = Path("ml/models")
RESULTS = Path("ml/results")


def make_model() -> Pipeline:
    features = FeatureUnion([
        ("words", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)),
        ("chars", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), sublinear_tf=True)),
    ])
    return Pipeline([("features", features), ("clf", LogisticRegression(C=10.0, max_iter=2000))])


def main() -> None:
    train = training_phrases()
    texts, labels = zip(*train)
    test_texts, test_labels = zip(*TEST_QUESTIONS)

    seen = {t.strip("!?. ") for t in texts}
    leaks = [q for q, _ in FRESH_TEST_QUESTIONS if q.lower().strip("!?. ") in seen]
    assert not leaks, f"fresh test questions found in training data: {leaks}"

    model = make_model().fit(texts, labels)
    pred = model.predict(test_texts)
    fresh_texts, fresh_labels = zip(*FRESH_TEST_QUESTIONS)
    fresh_pred = model.predict(fresh_texts)
    fresh_kw = [keyword_intent(t) for t in fresh_texts]
    # The advisor answers the top intent; when it is unsure (p < 0.6) it also shows the next 2 as buttons.
    proba, classes = model.predict_proba(fresh_texts), model.named_steps["clf"].classes_
    order = proba.argsort(axis=1)[:, ::-1]
    covered = [classes[o[0]] == y or (p.max() < 0.6 and y in classes[o[:3]]) for o, p, y in zip(order, proba, fresh_labels)]
    kw = [keyword_intent(t) for t in test_texts]

    results = {
        "train_phrases": len(train), "test_questions": len(TEST_QUESTIONS),
        "keyword_baseline": {"accuracy": round(accuracy_score(test_labels, kw), 3),
                             "macro_f1": round(f1_score(test_labels, kw, labels=INTENTS, average="macro"), 3)},
        "model": {"accuracy": round(accuracy_score(test_labels, pred), 3),
                  "macro_f1": round(f1_score(test_labels, pred, labels=INTENTS, average="macro"), 3)},
        "fresh_test": {"questions": len(FRESH_TEST_QUESTIONS),
                       "keyword_baseline_accuracy": round(accuracy_score(fresh_labels, fresh_kw), 3),
                       "model_accuracy": round(accuracy_score(fresh_labels, fresh_pred), 3),
                       "model_macro_f1": round(f1_score(fresh_labels, fresh_pred, labels=INTENTS, average="macro"), 3),
                       "answer_or_button_right": round(sum(covered) / len(covered), 3),
                       "unsure_share": round(float((proba.max(axis=1) < 0.6).mean()), 3),
                       "errors": [{"text": t, "true": y, "predicted": p} for t, y, p in zip(fresh_texts, fresh_labels, fresh_pred) if y != p]},
        "model_errors": [{"text": t, "true": y, "predicted": p}
                         for t, y, p in zip(test_texts, test_labels, pred) if y != p],
        "keyword_errors": [{"text": t, "true": y, "predicted": p}
                           for t, y, p in zip(test_texts, test_labels, kw) if y != p],
    }
    print(f"Train phrases: {len(train)}, test questions: {len(TEST_QUESTIONS)}")
    print(f"Keyword baseline: accuracy {results['keyword_baseline']['accuracy']}, "
          f"macro-F1 {results['keyword_baseline']['macro_f1']}")
    print(f"Model:            accuracy {results['model']['accuracy']}, macro-F1 {results['model']['macro_f1']}")
    print(f"Fresh test ({len(FRESH_TEST_QUESTIONS)} new questions): keywords {results['fresh_test']['keyword_baseline_accuracy']}, "
          f"model {results['fresh_test']['model_accuracy']}, answer or button right {results['fresh_test']['answer_or_button_right']}")
    for e in results["fresh_test"]["errors"]:
        print(f"  fresh error: {e['text']!r} -> {e['predicted']} (true {e['true']})")
    for e in results["model_errors"]:
        print(f"  model error: {e['text']!r} -> {e['predicted']} (true {e['true']})")

    MODELS.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODELS / "intent.joblib")
    (RESULTS / "intent.json").write_text(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
