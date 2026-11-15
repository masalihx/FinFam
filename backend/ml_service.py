"""Loads the trained models and answers ML questions for the web app."""
import sys
import threading
from datetime import datetime
from urllib.parse import urlparse

import joblib
import numpy as np
import pandas as pd

from backend.config import MODELS_DIR, PROCESSED_DIR, ROOT

sys.path.insert(0, str(ROOT / "ml"))
from live_features import FamilyState  # noqa: E402
from overspend_features import FORECAST_CATEGORIES, add_features  # noqa: E402
from text_utils import normalize  # noqa: E402

CORRECTION_WEIGHT = 5.0
RED_PROBABILITY = 0.75  # top ~20% riskiest situations on validation months (see docs/design.md)

# Stores whose category is clear from the website itself.
SITE_CATEGORIES = {
    "amazon.": "shopping", "walmart.": "shopping", "target.": "shopping", "ebay.": "shopping",
    "etsy.": "shopping", "bestbuy.": "shopping", "temu.": "shopping", "shein.": "shopping",
    "aliexpress.": "shopping", "wildberries.": "shopping", "kaspi.": "shopping", "ozon.": "shopping",
    "doordash.": "dining", "ubereats.": "dining", "grubhub.": "dining",
    "instacart.": "groceries", "wholefoodsmarket.": "groceries",
    "ticketmaster.": "entertainment", "steampowered.": "entertainment", "fandango.": "entertainment",
    "booking.": "travel", "expedia.": "travel", "airbnb.": "travel", "delta.": "travel", "united.": "travel",
    "sephora.": "personal_care", "ulta.": "personal_care",
    "cvs.": "health", "walgreens.": "health",
}


def merchant_key(text: str) -> str:
    return normalize(text)


class Categorizer:
    """TF-IDF + logistic regression, plus the family's own corrections."""

    def __init__(self):
        self.model = joblib.load(MODELS_DIR / "categorizer.joblib")
        self.lock = threading.Lock()
        self.retraining = False

    def predict(self, texts: list, corrections: dict) -> list:
        preds = list(self.model.predict(texts)) if texts else []
        # A correction for this exact merchant always wins.
        return [corrections.get(merchant_key(t), p) for t, p in zip(texts, preds)]

    def predict_spending(self, text: str) -> str:
        """Best category among the spending categories the overspend model knows."""
        proba = self.model.predict_proba([text])[0]
        classes = list(self.model.classes_)
        best = max(FORECAST_CATEGORIES, key=lambda c: proba[classes.index(c)] if c in classes else -1)
        return best

    def retrain_async(self, corrections: list) -> None:
        """Refit on the training data + corrections in a background thread."""
        if self.retraining or not corrections:
            return
        self.retraining = True

        def work():
            try:
                from train_categorizer import make_model  # imported lazily: heavy
                train = pd.read_parquet(PROCESSED_DIR / "descriptions_train.parquet")
                fixes = pd.DataFrame(corrections)
                texts = pd.concat([train["text"], fixes["example"]])
                labels = pd.concat([train["label"], fixes["category"]])
                weights = np.r_[np.ones(len(train)), np.full(len(fixes), CORRECTION_WEIGHT)]
                model = make_model().fit(texts, labels, clf__sample_weight=weights)
                with self.lock:
                    self.model = model
            finally:
                self.retraining = False

        threading.Thread(target=work, daemon=True).start()


class OverspendModel:
    def __init__(self):
        bundle = joblib.load(MODELS_DIR / "overspend.joblib")
        self.model = bundle["model"]
        self.threshold = float(bundle["threshold"])
        self.features = bundle["features"]

    def probability(self, row: pd.Series) -> float:
        return float(self.model.predict_proba(pd.DataFrame([row[self.features]]))[0, 1])

    def light(self, probability: float) -> str:
        if probability >= RED_PROBABILITY:
            return "red"
        if probability >= self.threshold:
            return "yellow"
        return "green"


def family_state(tx: pd.DataFrame, household_income: float, children: float) -> FamilyState:
    """FamilyState from the app's transaction table."""
    df = tx.rename(columns={"category": "label"}).assign(
        transaction_date=pd.to_datetime(tx["date"]), is_fraud=False)
    return FamilyState(df, household_income, children)


def features_with_budget(state: FamilyState, category: str, as_of: pd.Timestamp, extra: float,
                         budget_override=None):
    """Live features; a budget the family set by hand replaces the learned usual level."""
    row = state.features(category, as_of, extra)
    if row is None or budget_override is None:
        return row
    values = row.to_dict()
    values["budget"] = float(budget_override)
    return add_features(pd.DataFrame([values])).iloc[0]


def category_for_product(categorizer: Categorizer, title: str, url: str) -> str:
    host = urlparse(url or "").netloc.lower()
    for key, cat in SITE_CATEGORIES.items():
        if key in host:
            return cat
    site = host.replace("www.", "")
    return categorizer.predict_spending(f"[debit] {site} {title}")


def now() -> pd.Timestamp:
    return pd.Timestamp(datetime.now().date())
