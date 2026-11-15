"""Unified FinPilot categories and mappings from both source datasets.

Two independently generated datasets use different category names.
We map both onto one set so a model trained on one can be tested on the other.
"""

# Spending categories shown to families, plus income and transfers.
CATEGORIES = [
    "groceries",
    "dining",
    "transportation",
    "shopping",
    "housing",
    "utilities",
    "subscriptions",
    "entertainment",
    "health",
    "personal_care",
    "travel",
    "insurance",
    "education_childcare",
    "fees",
    "income",
    "transfer",
]

# Categories that count as everyday "wants" vs "needs" for the 50/30/20 baseline.
NEEDS = {"groceries", "transportation", "housing", "utilities", "health", "insurance", "education_childcare", "fees"}
WANTS = {"dining", "shopping", "subscriptions", "entertainment", "personal_care", "travel"}

# DoDataThings/us-bank-transaction-categories-v2 (training set).
DODATA_TO_UNIFIED = {
    "Groceries": "groceries",
    "Restaurants": "dining",
    "Transportation": "transportation",
    "Shopping": "shopping",
    "Rent": "housing",
    "Mortgage": "housing",
    "Utilities": "utilities",
    "Subscription": "subscriptions",
    "Entertainment": "entertainment",
    "Healthcare": "health",
    "Personal Care": "personal_care",
    "Travel": "travel",
    "Insurance": "insurance",
    "Education": "education_childcare",
    "Fees": "fees",
    "Income": "income",
    "Transfer": "transfer",
}

# misatadata/us-bank-transactions (family data, test set for categorization).
# Keys are (category, subcategory); "*" means any subcategory.
# Pairs that map to None have no counterpart in the training labels and are
# left out of the categorization test (cash withdrawals, charity, taxes, refunds, loans).
MISATA_TO_UNIFIED = {
    ("food_and_drink", "groceries"): "groceries",
    ("food_and_drink", "convenience"): "groceries",
    ("food_and_drink", "liquor_store"): "groceries",
    ("food_and_drink", "fast_food"): "dining",
    ("food_and_drink", "coffee"): "dining",
    ("food_and_drink", "restaurant"): "dining",
    ("food_and_drink", "food_delivery"): "dining",
    ("food_and_drink", "bar"): "dining",
    ("food_and_drink", "bakery"): "dining",
    ("food_and_drink", "membership"): "subscriptions",  # DashPass
    ("transportation", "*"): "transportation",
    ("shopping", "membership"): "subscriptions",  # Amazon Prime
    ("shopping", "veterinary"): "shopping",
    ("shopping", "*"): "shopping",
    ("housing", "*"): "housing",
    ("bills_utilities", "*"): "utilities",
    ("entertainment", "streaming"): "subscriptions",
    ("entertainment", "music"): "subscriptions",
    ("entertainment", "digital_services"): "subscriptions",
    ("entertainment", "fitness"): "personal_care",  # gyms are Personal Care in the training labels
    ("entertainment", "*"): "entertainment",
    ("software", "*"): "subscriptions",
    ("health", "*"): "health",
    ("personal_care", "*"): "personal_care",
    ("travel", "*"): "travel",
    ("insurance", "*"): "insurance",
    ("childcare", "*"): "education_childcare",
    ("bank_fees", "*"): "fees",
    ("income", "*"): "income",
    ("transfer_in", "*"): "transfer",
    ("transfer_out", "*"): "transfer",
    ("loan_payments", "credit_card_payment"): "transfer",
    ("loan_payments", "*"): None,
    ("cash", "*"): None,
    ("giving", "*"): None,
    ("government", "*"): None,
    ("refund", "*"): None,
}


def misata_category(category: str, subcategory: str):
    """Unified category for a misata (category, subcategory) pair, or None if excluded."""
    if (category, subcategory) in MISATA_TO_UNIFIED:
        return MISATA_TO_UNIFIED[(category, subcategory)]
    if (category, "*") in MISATA_TO_UNIFIED:
        return MISATA_TO_UNIFIED[(category, "*")]
    raise KeyError(f"No mapping for misata category {category!r}/{subcategory!r}")
