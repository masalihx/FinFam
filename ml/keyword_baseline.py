"""Keyword-rule baseline for categorization.

This is how many simple budgeting apps start: a hand-written list of brands
and words per category. The rules were written from general knowledge of US
merchants, without looking at the test data.
"""
import re

import pandas as pd

KEYWORDS = {
    "income": ["payroll", "dir dep", "direct dep", "salary", "ssa treas", "pension", "interest paid", "tax ref"],
    "transfer": ["zelle", "venmo", "transfer", "xfer", "payment thank", "autopay", "e-payment", "ach pmt", "cash app", "savings"],
    "fees": ["fee", "interest charge", "overdraft", "nsf"],
    "groceries": ["grocery", "market", "safeway", "kroger", "whole foods", "wholefds", "trader joe", "aldi", "publix",
                  "stop & shop", "7-eleven", "wegmans", "food lion", "heb"],
    "dining": ["restaurant", "cafe", "coffee", "starbucks", "mcdonald", "burger", "pizza", "taco", "chipotle", "subway",
               "doordash", "uber eats", "grubhub", "dunkin", "wendy", "chick-fil", "sushi", "grill", "kitchen", "bar "],
    "transportation": ["uber", "lyft", "shell", "chevron", "exxon", "gas", "fuel", "parking", "transit", "metro", "toll",
                       "car wash", "auto"],
    "shopping": ["amazon", "amzn", "target", "walmart", "costco", "best buy", "home depot", "lowe", "macy", "nordstrom",
                 "tj maxx", "ebay", "etsy", "store", "shop"],
    "housing": ["rent", "mortgage", "mtg", "property"],
    "utilities": ["electric", "energy", "water", "comcast", "xfinity", "verizon", "at&t", "t-mobile", "pg&e", "utility",
                  "internet", "wireless"],
    "subscriptions": ["netflix", "spotify", "hulu", "disney", "prime", "apple.com/bill", "youtube", "subscription", "hbo"],
    "entertainment": ["cinema", "theater", "theatre", "amc", "ticket", "steam", "playstation", "xbox", "concert"],
    "health": ["pharmacy", "cvs", "walgreens", "doctor", "dental", "clinic", "hospital", "medical", "health"],
    "personal_care": ["salon", "barber", "spa", "nail", "fitness", "gym", "laundry"],
    "travel": ["airline", "airlines", "hotel", "airbnb", "expedia", "delta", "united", "marriott", "hilton"],
    "insurance": ["insurance", "geico", "progressive", "state farm", "allstate"],
    "education_childcare": ["school", "tuition", "university", "college", "daycare", "kumon", "academy"],
}

# Checked in this order so that specific rules win over broad ones
# (for example "uber eats" is dining before "uber" is transportation).
ORDER = ["income", "transfer", "fees", "subscriptions", "dining", "groceries", "health", "insurance",
         "education_childcare", "housing", "utilities", "travel", "entertainment", "personal_care",
         "transportation", "shopping"]
FALLBACK = "shopping"

_PATTERNS = {cat: re.compile("|".join(re.escape(k) for k in KEYWORDS[cat])) for cat in ORDER}


def predict_one(text: str) -> str:
    low = text.lower()
    for cat in ORDER:
        if _PATTERNS[cat].search(low):
            return cat
    return FALLBACK


def predict(texts: pd.Series) -> list:
    return [predict_one(t) for t in texts]
