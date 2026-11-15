"""Demo family from the public synthetic dataset (misata, CC BY 4.0)."""
import pandas as pd

from backend.config import DEMO_ANCHOR_MONTH, DEMO_CUSTOMER, PROCESSED_DIR


def demo_transactions(today: pd.Timestamp) -> list:
    """The demo family's transactions, shifted so DEMO_ANCHOR_MONTH becomes the current month.

    Category labels from the dataset are NOT used: the app's own model categorizes them.
    Transactions after today are dropped, so the current month is partly spent.
    """
    tx = pd.read_parquet(PROCESSED_DIR / "household_tx.parquet")
    tx = tx[(tx["customer_id"] == DEMO_CUSTOMER) & ~tx["is_fraud"]].copy()
    shift = (today.to_period("M") - pd.Period(DEMO_ANCHOR_MONTH, "M")).n
    tx["date"] = tx["transaction_date"] + pd.DateOffset(months=shift)
    tx = tx[tx["date"] <= today]
    return [
        {"id": f"demo-{r.transaction_id}", "date": str(r.date.date()), "amount": float(r.amount),
         "description": r.description, "merchant": r.merchant_name, "channel": r.channel}
        for r in tx.itertuples()
    ]


def demo_profile() -> dict:
    c = pd.read_parquet(PROCESSED_DIR / "customers.parquet").set_index("customer_id").loc[DEMO_CUSTOMER]
    return {"family_name": "Demo family", "household_income": float(c["household_income"]),
            "children": int(c["children"]), "data_source": "demo"}


DEMO_GOALS = [
    {"name": "Kids' college fund", "target": 40000.0, "saved": 6000.0, "deadline": "2030-09-01"},
    {"name": "Family car", "target": 12000.0, "saved": 2500.0, "deadline": "2027-12-01"},
]
