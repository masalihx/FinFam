"""Gemini API (free tier): reads uploaded receipts/statements and estimates market prices.

Gemini never computes the family's numbers: it only turns files into rows and
gives one price opinion that our model blends with its own (weights from validation).
"""
import base64
import io
import json

import pandas as pd
import requests

from backend.config import GEMINI_API_KEY, GEMINI_MODEL

URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}


class GeminiError(RuntimeError):
    pass


def configured() -> bool:
    return bool(GEMINI_API_KEY)


def _call(parts: list, timeout: int = 120):
    if not configured():
        raise GeminiError("Gemini key is missing. Add GEMINI_API_KEY to .env.")
    try:
        resp = requests.post(URL.format(model=GEMINI_MODEL),
                             headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
                             json={"contents": [{"parts": parts}],
                                   "generationConfig": {"responseMimeType": "application/json", "temperature": 0}},
                             timeout=timeout)
    except requests.RequestException as e:
        raise GeminiError(f"Cannot reach Gemini: {e.__class__.__name__}")
    if resp.status_code != 200:
        raise GeminiError(f"Gemini returned {resp.status_code}: {resp.text[:200]}")
    try:
        return json.loads(resp.json()["candidates"][0]["content"]["parts"][-1]["text"])
    except (KeyError, IndexError, ValueError):
        raise GeminiError("Gemini gave an answer FinPilot could not read. Try again.")


EXTRACT_PROMPT = (
    "You read personal finance documents: store receipts, bank or card statements, or spreadsheets of expenses. "
    "Extract every money movement as a JSON object with keys: date (YYYY-MM-DD; use {today} if missing), "
    "description (merchant or payee, short), amount (number; NEGATIVE for money spent, POSITIVE for money received), "
    "items (for a receipt: up to 5 main item names, otherwise empty list). "
    "For a single receipt return one row with the TOTAL paid. Ignore running balances and subtotals. "
    "Answer only with a JSON object: {{\"document_type\": \"receipt|statement|spreadsheet|other\", \"rows\": [...]}}."
)


def extract_transactions(filename: str, content: bytes, mime: str, today: str) -> dict:
    """Rows found in an uploaded file (image, PDF, CSV or Excel)."""
    prompt = EXTRACT_PROMPT.format(today=today)
    name = filename.lower()
    if name.endswith((".csv", ".xlsx", ".xls")):
        try:
            df = pd.read_csv(io.BytesIO(content)) if name.endswith(".csv") else pd.read_excel(io.BytesIO(content))
        except Exception:
            raise GeminiError("Could not read this table. Save it as CSV or XLSX and try again.")
        text = df.head(400).to_csv(index=False)
        parts = [{"text": prompt}, {"text": f"Spreadsheet '{filename}':\n{text}"}]
    elif mime in IMAGE_TYPES or mime == "application/pdf" or name.endswith(".pdf"):
        parts = [{"text": prompt},
                 {"inline_data": {"mime_type": "application/pdf" if name.endswith(".pdf") else mime,
                                  "data": base64.b64encode(content).decode()}}]
    else:
        raise GeminiError("Upload a photo (JPG, PNG, WEBP, HEIC), a PDF, or a CSV/Excel table.")
    out = _call(parts, timeout=180)
    rows = []
    for r in out.get("rows", []):
        try:
            amount = float(r.get("amount"))
            date = str(pd.Timestamp(r.get("date") or today).date())
        except (TypeError, ValueError):
            continue
        desc = str(r.get("description") or "Unknown").strip()[:120]
        items = [str(i)[:60] for i in (r.get("items") or [])][:5]
        rows.append({"date": date, "description": desc, "amount": round(amount, 2), "items": items})
    return {"document_type": out.get("document_type", "other"), "rows": rows}


def estimate_price(title: str, category_hint: str = "") -> float:
    """Gemini's opinion of the typical US price of a product (2023 prices, like the training data)."""
    prompt = ("Estimate the typical US Amazon price in 2023 (USD) for this product. "
              "Answer only with a JSON number.\n\n" + (f"[{category_hint}] " if category_hint else "") + title[:200])
    value = _call([{"text": prompt}], timeout=20)
    if isinstance(value, dict):
        value = next(iter(value.values()))
    return float(value)
