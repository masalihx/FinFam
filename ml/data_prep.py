"""Step 1 of FinPilot: download raw data and build clean, unified tables.

Run from the project root:
    .venv/bin/python ml/data_prep.py
"""
import sys
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from categories import CATEGORIES, DODATA_TO_UNIFIED, misata_category  # noqa: E402

RAW = Path("data/raw")
PROCESSED = Path("data/processed")

HF = "https://huggingface.co/datasets"
SOURCES = {
    "bank_descriptions_v2.csv": f"{HF}/DoDataThings/us-bank-transaction-categories-v2/resolve/main/transactions-synthetic.csv",
    "household_transactions.parquet": f"{HF}/misatadata/us-bank-transactions/resolve/main/data/transactions.parquet",
    "customers.parquet": f"{HF}/misatadata/us-bank-transactions/resolve/main/data/customers.parquet",
    "recurring_streams.parquet": f"{HF}/misatadata/us-bank-transactions/resolve/main/data/recurring_streams.parquet",
}

# Columns kept from the family data. Personal names and emails are dropped:
# the data is synthetic, but the app does not need them.
TX_COLUMNS = [
    "transaction_id", "customer_id", "account_id", "transaction_date", "amount",
    "description", "merchant_name", "category", "subcategory", "channel",
    "stream_id", "is_fraud",
]
CUSTOMER_COLUMNS = [
    "customer_id", "age", "household_income", "income_quintile", "housing",
    "earners", "married", "children", "vehicles", "metro_name",
]


def download_raw() -> None:
    """Download each source file once."""
    RAW.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        path = RAW / name
        if path.exists() and path.stat().st_size > 0:
            continue
        print(f"Downloading {name} ...")
        urllib.request.urlretrieve(url, path)


def with_sign_prefix(description: pd.Series, amount: pd.Series) -> pd.Series:
    """Add the '[debit]'/'[credit]' prefix used by the training data."""
    prefix = amount.lt(0).map({True: "[debit] ", False: "[credit] "})
    return prefix + description.fillna("").str.strip()


def build_descriptions() -> pd.DataFrame:
    """Training set for categorization, with unified labels."""
    raw = pd.read_csv(RAW / "bank_descriptions_v2.csv")
    out = raw.assign(label=raw["category"].map(DODATA_TO_UNIFIED))
    unmapped = out.loc[out["label"].isna(), "category"].unique()
    if len(unmapped):
        raise ValueError(f"Unmapped training categories: {unmapped}")
    return out.rename(columns={"description": "text"})[["text", "label"]]


def build_household_transactions() -> pd.DataFrame:
    """Family transactions with unified labels and model-ready text."""
    raw = pd.read_parquet(RAW / "household_transactions.parquet", columns=TX_COLUMNS)
    pairs = raw[["category", "subcategory"]].drop_duplicates()
    pairs["label"] = [misata_category(c, s) for c, s in zip(pairs["category"], pairs["subcategory"])]
    out = raw.merge(pairs, on=["category", "subcategory"], how="left")
    return out.assign(
        transaction_date=pd.to_datetime(out["transaction_date"]),
        text=with_sign_prefix(out["description"], out["amount"]),
        is_recurring=out["stream_id"].notna(),
    ).sort_values(["customer_id", "transaction_date", "transaction_id"]).reset_index(drop=True)


def main() -> None:
    download_raw()
    PROCESSED.mkdir(parents=True, exist_ok=True)

    descriptions = build_descriptions()
    descriptions.to_parquet(PROCESSED / "descriptions_train.parquet", index=False)
    print(f"Training descriptions: {len(descriptions):,}, {descriptions['label'].nunique()} categories")

    tx = build_household_transactions()
    tx.to_parquet(PROCESSED / "household_tx.parquet", index=False)
    labelled = tx["label"].notna()
    print(f"Family transactions: {len(tx):,} ({labelled.mean():.1%} have a unified category)")

    customers = pd.read_parquet(RAW / "customers.parquet", columns=CUSTOMER_COLUMNS)
    customers.to_parquet(PROCESSED / "customers.parquet", index=False)
    print(f"Families: {len(customers)}")

    missing = set(CATEGORIES) - set(tx.loc[labelled, "label"])
    if missing:
        print(f"Warning: categories absent from family data: {sorted(missing)}")


if __name__ == "__main__":
    main()
