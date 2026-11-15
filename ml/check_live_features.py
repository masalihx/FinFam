"""Check that live features match the training features on check days.

Run from the project root:
    .venv/bin/python ml/check_live_features.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from live_features import FamilyState  # noqa: E402
from overspend_features import FEATURES  # noqa: E402

PROCESSED = Path("data/processed")


def main() -> None:
    tx = pd.read_parquet(PROCESSED / "household_tx.parquet")
    customers = pd.read_parquet(PROCESSED / "customers.parquet").set_index("customer_id")
    ex = pd.read_parquet(PROCESSED / "overspend_examples.parquet")
    sample = ex.sample(300, random_state=0)

    states, worst = {}, {f: 0.0 for f in FEATURES}
    for row in sample.itertuples():
        cid = row.customer_id
        if cid not in states:
            c = customers.loc[cid]
            states[cid] = FamilyState(tx[tx["customer_id"] == cid], c["household_income"], c["children"])
        as_of = row.month.to_timestamp() + pd.Timedelta(days=row.day - 1)
        live = states[cid].features(row.label, as_of)
        if live is None:
            raise AssertionError(f"No live features for {cid} {row.label} {row.month} day {row.day}")
        for f in FEATURES:
            a, b = float(getattr(row, f)), float(live[f])
            worst[f] = max(worst[f], abs(a - b) / max(1.0, abs(a)))

    bad = {f: round(v, 4) for f, v in worst.items() if v > 1e-6}
    print("All features match." if not bad else f"Mismatched features (max relative diff): {bad}")


if __name__ == "__main__":
    main()
