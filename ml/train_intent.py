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
from intents import INTENTS, TEST_QUESTIONS, keyword_intent, training_phrases  # noqa: E402

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

    model = make_model().fit(texts, labels)
    pred = model.predict(test_texts)
    kw = [keyword_intent(t) for t in test_texts]

    results = {
        "train_phrases": len(train), "test_questions": len(TEST_QUESTIONS),
        "keyword_baseline": {"accuracy": round(accuracy_score(test_labels, kw), 3),
                             "macro_f1": round(f1_score(test_labels, kw, labels=INTENTS, average="macro"), 3)},
        "model": {"accuracy": round(accuracy_score(test_labels, pred), 3),
                  "macro_f1": round(f1_score(test_labels, pred, labels=INTENTS, average="macro"), 3)},
        "model_errors": [{"text": t, "true": y, "predicted": p}
                         for t, y, p in zip(test_texts, test_labels, pred) if y != p],
        "keyword_errors": [{"text": t, "true": y, "predicted": p}
                           for t, y, p in zip(test_texts, test_labels, kw) if y != p],
    }
    print(f"Train phrases: {len(train)}, test questions: {len(TEST_QUESTIONS)}")
    print(f"Keyword baseline: accuracy {results['keyword_baseline']['accuracy']}, "
          f"macro-F1 {results['keyword_baseline']['macro_f1']}")
    print(f"Model:            accuracy {results['model']['accuracy']}, macro-F1 {results['model']['macro_f1']}")
    for e in results["model_errors"]:
        print(f"  model error: {e['text']!r} -> {e['predicted']} (true {e['true']})")

    MODELS.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODELS / "intent.joblib")
    (RESULTS / "intent.json").write_text(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
