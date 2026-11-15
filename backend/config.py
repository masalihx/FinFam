"""Paths and settings. Secrets come from the .env file (never committed)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "finpilot.db"
WEB_DIR = ROOT / "web"
MODELS_DIR = ROOT / "ml" / "models"
PROCESSED_DIR = ROOT / "data" / "processed"

DEMO_CUSTOMER = "C000369"      # married couple, 2 children, $117,700 household income, 24 months of data
DEMO_ANCHOR_MONTH = "2026-08"  # dataset month shown as "this month" (a busy shopping month for this family)


def _load_env(path: Path) -> None:
    """Minimal .env reader: KEY=value lines; values already in the environment win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_env(ROOT / ".env")

PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = os.environ.get("PAYPAL_CLIENT_SECRET", "")
PAYPAL_MODE = os.environ.get("PAYPAL_MODE", "sandbox")
PAYPAL_API = "https://api-m.sandbox.paypal.com" if PAYPAL_MODE == "sandbox" else "https://api-m.paypal.com"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
