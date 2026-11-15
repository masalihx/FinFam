"""Loads the trained models and answers ML questions for the web app."""
import re
import sys
import threading
from datetime import datetime
from urllib.parse import urlparse

import joblib
import numpy as np
import pandas as pd

from backend import gemini
from backend.config import MODELS_DIR, PROCESSED_DIR, ROOT

sys.path.insert(0, str(ROOT / "ml"))
from categories import NEEDS, WANTS  # noqa: E402
from live_features import FamilyState  # noqa: E402
from overspend_features import FORECAST_CATEGORIES, add_features  # noqa: E402
from recurring import build_series, next_occurrence  # noqa: E402
from text_utils import normalize  # noqa: E402

CORRECTION_WEIGHT = 5.0

# Stores whose category is clear from the website itself.
SITE_CATEGORIES = {
    "amazon.": "shopping", "walmart.": "shopping", "target.": "shopping", "ebay.": "shopping", "etsy.": "shopping",
    "bestbuy.": "shopping", "temu.": "shopping", "shein.": "shopping", "aliexpress.": "shopping", "nike.": "shopping",
    "doordash.": "dining", "ubereats.": "dining", "grubhub.": "dining",
    "instacart.": "groceries", "wholefoodsmarket.": "groceries",
    "ticketmaster.": "entertainment", "stubhub.": "entertainment", "steampowered.": "entertainment",
    "fandango.": "entertainment", "livenation.": "entertainment",
    "booking.": "travel", "expedia.": "travel", "airbnb.": "travel", "delta.": "travel", "united.": "travel",
    "sephora.": "personal_care", "ulta.": "personal_care", "cvs.": "health", "walgreens.": "health",
}
# Words in a product title that point to a category other than general shopping.
TITLE_KEYWORDS = {
    "education_childcare": ["textbook", "school supplies", "backpack for school", "calculator", "notebook", "pencil",
                            "tuition", "course"],
    "health": ["vitamin", "supplement", "medicine", "first aid", "thermometer", "allergy", "pain relief"],
    "groceries": ["grocery", "snack", "coffee beans", "cereal", "pantry", "beverage", "organic food"],
    "entertainment": ["ticket", "concert", "festival", "game pass", "video game", "playstation", "xbox", "nintendo",
                      "movie"],
    "travel": ["flight", "hotel", "airfare", "vacation package"],
    "personal_care": ["shampoo", "skincare", "makeup", "cosmetic", "perfume", "razor"],
    "subscriptions": ["subscription", "membership", "monthly plan"],
    "dining": ["restaurant", "meal delivery", "pizza", "burger"],
}
# Amazon dataset category used as a hint for the price model.
PRICE_CATEGORY_HINT = {
    "shopping": "Amazon Home", "entertainment": "Video Games", "health": "Health & Personal Care",
    "personal_care": "All Beauty", "education_childcare": "Office Products", "groceries": "Grocery",
}


def merchant_key(text: str) -> str:
    return normalize(text)


def with_sign(amount: float, description: str) -> str:
    return ("[debit] " if amount < 0 else "[credit] ") + description


class Categorizer:
    """TF-IDF + logistic regression, plus the family's own corrections."""

    def __init__(self):
        self.model = joblib.load(MODELS_DIR / "categorizer.joblib")
        self.lock = threading.Lock()
        self.retraining = False

    def predict(self, texts: list, corrections: dict) -> list:
        with self.lock:
            preds = list(self.model.predict(texts)) if texts else []
        return [corrections.get(merchant_key(t), p) for t, p in zip(texts, preds)]

    def retrain_async(self, corrections: list) -> None:
        if self.retraining or not corrections:
            return
        self.retraining = True

        def work():
            try:
                from train_categorizer import make_model  # heavy import, only when needed
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


class PriceModel:
    """Market price range: our title model blended with Gemini (weight chosen on validation)."""

    def __init__(self):
        b = joblib.load(MODELS_DIR / "price.joblib")
        self.model = b["model"]
        self.per_cat, self.overall = b["per_cat"], b["overall"]
        self.weight = float(b.get("blend_weight", 1.0))
        self.band = b.get("hybrid_band", self.overall)

    def ours(self, title: str, hint: str) -> float:
        clean = re.sub(r"\s+", " ", title).strip().lower()
        text = f"{hint} | {clean}"
        return float(np.exp(self.model.predict([text])[0]))

    def estimate(self, title: str, category: str, cached_gemini=None) -> dict:
        hint = PRICE_CATEGORY_HINT.get(category, "Amazon Home")
        ours = self.ours(title, hint)
        g, source = cached_gemini, "hybrid"
        if g is None:
            try:
                g = gemini.estimate_price(title, hint)
            except (gemini.GeminiError, ValueError, TypeError):
                g = None
        if g and g > 0:
            mid = float(np.exp(self.weight * np.log(ours) + (1 - self.weight) * np.log(g)))
            lo_q, hi_q = self.band
        else:
            mid, source = ours, "our model only (Gemini unavailable)"
            lo_q, hi_q = self.per_cat.get(hint, self.overall)
        return {"low": round(mid * float(np.exp(lo_q)), 2), "high": round(mid * float(np.exp(hi_q)), 2),
                "typical": round(mid, 2), "our_model": round(ours, 2), "gemini": g, "source": source,
                "prices_as_of": 2023}


BANK_WORDS = {"ach", "electronic", "debit", "credit", "pay", "org", "card", "purchase", "recurring", "web", "ppd",
              "online", "payment", "des", "indn", "co", "pmt", "auto", "ca", "wa", "ny", "tx", "fl", "il", "ma"}


def pretty_name(key: str, merchant=None) -> str:
    """Readable payee name: the merchant if known, otherwise the key without bank words."""
    if isinstance(merchant, str) and merchant.strip() and merchant.strip().lower() not in ("zelle", "venmo", "paypal"):
        return merchant.strip()[:40]
    low = key.lower()
    m = re.search(r"name:\s*([a-z]+(?:\s[a-z]+)?)", low)
    if "zelle" in low and m:
        return f"Zelle to {m.group(1).title()}"
    words = [w for w in re.split(r"[\s*]+", low) if w and w not in BANK_WORDS and ":" not in w and len(w) > 1]
    return " ".join(words[:3]).title() or key.title()[:40]


class RecurringModel:
    def __init__(self):
        b = joblib.load(MODELS_DIR / "recurring.joblib")
        self.model, self.features = b["model"], b["features"]

    def upcoming(self, df: pd.DataFrame, today: pd.Timestamp, days: int = 30) -> list:
        """Recurring series in the family's data and their next expected payment."""
        if df.empty:
            return []
        tx = df.rename(columns={"room_id": "family"})[["family", "date", "amount", "description", "member_id"]]
        tx = tx[tx["date"] <= today]
        series = build_series(tx.assign(customer_id=tx["family"]), min_n=3)
        if series.empty:
            return []
        prob = self.model.predict_proba(series[self.features])[:, 1]
        series = series.assign(prob=prob)
        out = []
        for r in series[series["prob"] >= 0.5].itertuples():
            if (today - r.last_date).days > max(45, 2.5 * r.gap_median):
                continue  # stopped
            nxt = next_occurrence(r.last_date, r.gap_median, today)
            if (nxt - today).days > days:
                continue
            freq = ("weekly" if r.gap_median <= 9 else "every 2 weeks" if r.gap_median <= 18
                    else "monthly" if r.gap_median <= 40 else "yearly" if r.gap_median > 300 else f"every {r.gap_median:.0f} days")
            match = df[df["description"] == r.example]
            merchant = match["merchant"].dropna().iloc[-1] if len(match) and match["merchant"].notna().any() else None
            out.append({"date": str(nxt.date()), "name": pretty_name(r.key, merchant), "amount": round(float(r.median_amount), 2),
                        "frequency": freq, "confidence": round(float(r.prob), 2), "example": r.example,
                        "category": match["category"].iloc[-1] if len(match) else None,
                        "member_id": int(match["member_id"].iloc[-1]) if len(match) and pd.notna(match["member_id"].iloc[-1]) else None})
        return sorted(out, key=lambda x: x["date"])


def family_state(df: pd.DataFrame, household_income: float, children: int) -> FamilyState:
    """The overspend model also uses yearly household income and number of children."""
    d = df.rename(columns={"category": "label"}).assign(transaction_date=df["date"], is_fraud=False)
    return FamilyState(d, float(household_income), float(children))


def yearly_income(df: pd.DataFrame, today: pd.Timestamp) -> float:
    """Household income over the last 12 months (family members' income only, no transfers)."""
    last = df[(df["date"] > today - pd.DateOffset(months=12)) & (df["category"] == "income")]
    months = max(1, min(12, df["date"].dt.to_period("M").nunique()))
    return float(last["amount"].sum() * 12 / months)


def features_with_budget(state: FamilyState, category: str, as_of: pd.Timestamp, extra: float, budget_override=None):
    """Live features; a limit the family set replaces the learned usual level."""
    row = state.features(category, as_of, extra)
    if row is None or budget_override is None:
        return row
    values = row.to_dict()
    values["budget"] = float(budget_override)
    return add_features(pd.DataFrame([values])).iloc[0]


def category_for_product(title: str, url: str) -> str:
    host = urlparse(url or "").netloc.lower()
    for key, cat in SITE_CATEGORIES.items():
        if key in host:
            low = (title or "").lower()
            # A ticket bought on Amazon is still entertainment, school supplies are still education.
            for c, words in TITLE_KEYWORDS.items():
                if c in ("education_childcare", "health", "entertainment") and any(w in low for w in words):
                    return c
            return cat
    low = (title or "").lower()
    for cat, words in TITLE_KEYWORDS.items():
        if any(w in low for w in words):
            return cat
    return "shopping"


def default_kind(category: str) -> str:
    return "need" if category in NEEDS else "want" if category in WANTS else "other"


def now() -> pd.Timestamp:
    return pd.Timestamp(datetime.now().date())
