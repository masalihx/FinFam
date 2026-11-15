"""Text cleaning shared by training and the web app.

Banks wrap the merchant name in their own boilerplate ("Card Purchase 10/08 ...
Card 1693", "CHECKCARD 1219 ..."). That boilerplate says nothing about the
category, and the training data does not have it, so we strip it.
The wrapper list follows the published statement formats of large US banks.
"""
import re

_WRAPPERS = [
    r"recurring card purchase(?: with pin)?",
    r"recurring payment authorized on",
    r"purchase authorized on",
    r"debit card purchase",
    r"card purchase(?: with pin)?(?! return)",
    r"checkcard",
    r"(?<=\] )purchase(?! interest)",  # Bank of America "PURCHASE 1206 ..."
    r"\bcard \d{4}\b",
    r"\bs\d{9,}\b",            # Wells Fargo reference numbers
    r"#\s?\d+",                # store and terminal numbers
    r"\b\d{1,2}[:/]\d{2}[ap]?\b",  # dates and times like 10/08 or 4:47p
]
_WRAPPER_RE = re.compile("|".join(_WRAPPERS))
_DIGITS_RE = re.compile(r"\d+")
_SPACES_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Lowercase, drop bank boilerplate, and replace remaining digit runs with 0."""
    low = text.lower()
    low = _WRAPPER_RE.sub(" ", low)
    low = _DIGITS_RE.sub("0", low)
    return _SPACES_RE.sub(" ", low).strip()
