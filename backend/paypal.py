"""PayPal Sandbox import (test accounts, no real money).

Uses the Transaction Search API. In the PayPal developer dashboard the app
needs the "Transaction search" feature enabled. Sandbox transactions can take
a few hours to appear in search results.
"""
from datetime import datetime, timedelta, timezone

import requests

from backend.config import PAYPAL_API, PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET

TIMEOUT = 20
MAX_RANGE_DAYS = 31  # API limit per request


class PayPalError(RuntimeError):
    pass


def configured() -> bool:
    return bool(PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET)


def _token() -> str:
    resp = requests.post(f"{PAYPAL_API}/v1/oauth2/token", auth=(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET),
                         data={"grant_type": "client_credentials"}, timeout=TIMEOUT)
    if resp.status_code != 200:
        raise PayPalError(f"PayPal sign-in failed ({resp.status_code}). Check the keys in .env.")
    return resp.json()["access_token"]


def _describe(t: dict) -> str:
    info = t.get("transaction_info", {})
    items = (t.get("cart_info") or {}).get("item_details") or []
    payer = ((t.get("payer_info") or {}).get("payer_name") or {}).get("alternate_full_name")
    what = (items[0].get("item_name") if items else None) or info.get("transaction_subject") \
        or info.get("transaction_note") or payer or "PayPal transaction"
    return f"PAYPAL *{what}"


def fetch_transactions(days: int = 90) -> list:
    """Transactions of the sandbox account for the last `days` days, in the app's format."""
    if not configured():
        raise PayPalError("PayPal keys are missing. Add PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET to .env.")
    headers = {"Authorization": f"Bearer {_token()}"}
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    out = []
    while start < end:
        chunk_end = min(end, start + timedelta(days=MAX_RANGE_DAYS))
        page = 1
        while True:
            params = {"start_date": start.strftime("%Y-%m-%dT%H:%M:%S-0000"),
                      "end_date": chunk_end.strftime("%Y-%m-%dT%H:%M:%S-0000"),
                      "fields": "all", "page_size": 500, "page": page}
            resp = requests.get(f"{PAYPAL_API}/v1/reporting/transactions", headers=headers,
                                params=params, timeout=TIMEOUT)
            if resp.status_code == 403:
                raise PayPalError("PayPal refused Transaction Search. Enable 'Transaction search' "
                                  "for the app in the developer dashboard.")
            if resp.status_code != 200:
                raise PayPalError(f"PayPal returned {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            for t in data.get("transaction_details", []):
                info = t.get("transaction_info", {})
                amount = float((info.get("transaction_amount") or {}).get("value", 0))
                out.append({
                    "id": f"pp-{info.get('transaction_id')}",
                    "date": info.get("transaction_initiation_date", "")[:10],
                    "amount": amount,
                    "description": _describe(t),
                    "merchant": None, "channel": "online",
                })
            if page >= int(data.get("total_pages", 1) or 1):
                break
            page += 1
        start = chunk_end
    return out
