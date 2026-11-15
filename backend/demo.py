"""Demo family room: the Carters (2 parents + 2 teens).

- The family bank is a synthetic household from an open dataset
  (Misata "US Bank and Card Transactions", CC BY 4.0), connected by Alex.
- The dataset does not say which family member made each payment, so the teens'
  own money (pay, allowance, spending) is generated here with a fixed seed.
  The write-up says so.
Demo logins use the reserved .example domain; the shared demo password below is
for local testing only.
"""
from datetime import datetime

import numpy as np
import pandas as pd

from backend.config import DEMO_ANCHOR_MONTH, DEMO_CUSTOMER, PROCESSED_DIR

DEMO_PASSWORD = "carter-demo-2026"
FAMILY = [
    {"key": "alex", "email": "alex@carter.example", "name": "Alex Carter", "role": "parent"},
    {"key": "sam", "email": "sam@carter.example", "name": "Sam Carter", "role": "parent"},
    {"key": "maya", "email": "maya@carter.example", "name": "Maya Carter", "role": "teen",
     "allowance": (40.0, "month")},
    {"key": "leo", "email": "leo@carter.example", "name": "Leo Carter", "role": "teen",
     "allowance": (25.0, "week")},
]
ROOM_NAME = "The Carter family"

FAMILY_GOALS = [
    {"name": "Kids' college fund", "target": 40000.0, "saved": 6000.0, "deadline": "2030-09-01"},
    {"name": "Family car", "target": 12000.0, "saved": 2500.0, "deadline": "2027-12-01"},
]
PERSONAL_GOALS = {
    "maya": [{"name": "First car", "target": 3000.0, "saved": 900.0, "deadline": "2027-06-01"}],
    "leo": [{"name": "Gaming PC", "target": 900.0, "saved": 220.0, "deadline": "2027-03-01"}],
}

# Teen spending patterns: (description, mean amount, purchases per month).
TEEN_SHOPS = {
    "maya": [("SHEIN.COM", 38, 1.2), ("TARGET T-2201 FONTANA CA", 26, 1.0), ("CHIPOTLE 2291 FONTANA CA", 13, 2.5),
             ("STARBUCKS STORE 52211 FONTANA CA", 7, 4.0), ("ULTA BEAUTY #1123", 24, 0.6),
             ("AMC 2201 ONLINE", 16, 0.6), ("UBER *TRIP HELP.UBER.COM", 14, 1.0)],
    "leo": [("STEAMGAMES.COM 4259522985", 18, 0.8), ("ROBLOX CORPORATION", 10, 1.2), ("MCDONALD'S F3321 FONTANA CA", 8, 3.0),
            ("7-ELEVEN 12822 FONTANA CA", 5, 3.0), ("GAMESTOP #4412", 30, 0.3), ("NIKE.COM", 70, 0.15)],
}


def month_shift(today: pd.Timestamp) -> int:
    return (today.to_period("M") - pd.Period(DEMO_ANCHOR_MONTH, "M")).n


def family_bank(today: pd.Timestamp) -> list:
    """The household's transactions, shifted so the anchor month is the current month."""
    tx = pd.read_parquet(PROCESSED_DIR / "household_tx.parquet")
    tx = tx[(tx["customer_id"] == DEMO_CUSTOMER) & ~tx["is_fraud"]].copy()
    tx["date"] = tx["transaction_date"] + pd.DateOffset(months=month_shift(today))
    tx = tx[tx["date"] <= today]
    return [{"id": f"demo-{r.transaction_id}", "date": str(r.date.date()), "amount": float(r.amount),
             "description": r.description, "merchant": r.merchant_name, "channel": r.channel}
            for r in tx.itertuples()]


def teen_transactions(key: str, today: pd.Timestamp) -> list:
    """Synthetic pay, allowance and spending for one teen over the same 24 months."""
    rng = np.random.default_rng(11 if key == "maya" else 23)
    start = (today.to_period("M") - 23).to_timestamp()
    days = pd.date_range(start, today, freq="D")
    out = []

    def add(date, amount, desc, channel):
        out.append({"id": f"demo-{key}-{len(out):05d}", "date": str(pd.Timestamp(date).date()),
                    "amount": round(float(amount), 2), "description": desc, "merchant": None, "channel": channel})

    if key == "maya":
        for d in days[days.weekday == 4][::2]:  # every other Friday
            add(d, rng.normal(185, 25), "RIVERSIDE CAFE PAYROLL DIR DEP", "ach")
        for d in days[days.day == 1]:
            add(d, 40.0, "ALLOWANCE FROM ALEX CARTER", "internal")
            add(d + pd.Timedelta(days=4), -11.99, "SPOTIFY USA", "online")
    else:
        for d in days[days.weekday == 0]:  # every Monday
            add(d, 25.0, "ALLOWANCE FROM ALEX CARTER", "internal")
        for d in days[days.day == 9]:
            add(d, -4.99, "ROBLOX PREMIUM MEMBERSHIP", "online")
        for d in pd.date_range(start, today, freq="MS")[::3]:
            add(d + pd.Timedelta(days=rng.integers(0, 25)), rng.normal(60, 15), "BIRTHDAY GIFT FROM GRANDMA" if d.month == 4
                else "NEIGHBOR LAWN MOWING", "p2p")
    for desc, mean, per_month in TEEN_SHOPS[key]:
        n = rng.poisson(per_month * len(days) / 30.4)
        for d in rng.choice(days, size=n):
            amount = max(1.5, rng.gamma(4, mean / 4))
            channel = "online" if any(w in desc for w in (".COM", "ONLINE", "UBER", "ROBLOX")) else "in_store"
            add(d, -amount, desc, channel)
    return [t for t in out if t["date"] <= str(today.date())]


# Category fixes the family already made (each one re-labels every payment from that merchant).
SEED_CORRECTIONS = [
    ("[debit] PURCHASE INTEREST CHARGE", "fees"),
    ("[debit] Debit Card Purchase 8:06p #9748 MACYS RIVERSIDE RIVERSIDE CA", "shopping"),
]

PLANS = [  # upcoming one-off expenses the family typed in (relative to today)
    {"name": "Leo's birthday party", "amount": 150.0, "days_ahead": 12, "member": "leo"},
    {"name": "Holiday gifts", "amount": 400.0, "days_ahead": 30, "member": None},
]


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
