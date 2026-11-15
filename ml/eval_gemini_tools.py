"""Does teaching Gemini through context help? Tool-choice accuracy on the 47 separately written test questions.

(A) Gemini + our teaching context (family facts, rules, examples from our intent dataset) + our tools
(B) Gemini + the same tools, no teaching context (zero-shot)
(C) our intent model (TF-IDF + logistic regression), mapped to the same tools

Correct = the first tool Gemini calls (or "no tool" for greetings) matches the question's labelled intent.

    .venv/bin/python ml/eval_gemini_tools.py
"""
import json
import sys
import time
from pathlib import Path

import joblib
import requests

sys.path.insert(0, str(Path(__file__).parent))
from intents import TEST_QUESTIONS  # noqa: E402
from price_hybrid import gemini_key  # noqa: E402

MODEL = "gemini-3.5-flash-lite"  # the extension default; gemini-3.5-flash allows only 20 free requests a day
SPEC = json.loads(Path("extension/data/assistant_spec.json").read_text())
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
PAUSE = 7  # free tier: stay under the per-minute limit


def taught_instruction() -> str:
    return (SPEC["instruction"].replace("{today}", "2026-11-15")
            .replace("{family}", "The Carter family; Alex (parent), Sam (parent), Maya (teen), Leo (teen)")
            .replace("{me}", "Alex, a parent")
            .replace("{needs_wants}", "Groceries: need; Housing: need; Shopping: want (limit $900/month); Dining & coffee: want (limit $970/month)")
            .replace("{examples}", "\n".join(f'  "{e["q"]}" -> {e["tool"] or "no tool"}' for e in SPEC["examples"]))
            .replace("{categories}", "groceries, dining, shopping, transportation, entertainment, ..."))


def first_tool(question: str, taught: bool):
    body = {"contents": [{"role": "user", "parts": [{"text": question}]}],
            "tools": [{"functionDeclarations": SPEC["tools"]}], "generationConfig": {"temperature": 0}}
    if taught:
        body["systemInstruction"] = {"parts": [{"text": taught_instruction()}]}
    for attempt in range(4):
        r = requests.post(URL, headers={"x-goog-api-key": gemini_key()}, json=body, timeout=120)
        if r.status_code == 429:
            time.sleep(20 * (attempt + 1))
            continue
        r.raise_for_status()
        parts = r.json()["candidates"][0]["content"].get("parts", [])
        calls = [p["functionCall"]["name"] for p in parts if "functionCall" in p]
        return calls[0] if calls else None
    raise RuntimeError("Gemini rate limit")


def main() -> None:
    expected = [SPEC["intent_tool"][intent] for _, intent in TEST_QUESTIONS]
    intent_model = joblib.load("ml/models/intent.joblib")
    ours = [SPEC["intent_tool"][p] for p in intent_model.predict([q for q, _ in TEST_QUESTIONS])]
    rows = []
    for (q, intent), exp, our in zip(TEST_QUESTIONS, expected, ours):
        a = first_tool(q, taught=True)
        time.sleep(PAUSE)
        b = first_tool(q, taught=False)
        time.sleep(PAUSE)
        rows.append({"question": q, "expected": exp, "taught": a, "zero_shot": b, "intent_model": our})
        print(f"{q[:45]:<45} exp={exp} taught={a} zero={b} ours={our}", flush=True)
    acc = lambda key: round(sum(r[key] == r["expected"] for r in rows) / len(rows), 3)  # noqa: E731
    out = {"model": MODEL, "questions": len(rows), "accuracy": {"gemini_taught": acc("taught"), "gemini_zero_shot": acc("zero_shot"),
                                                               "intent_model": acc("intent_model")},
           "rows": rows}
    print(json.dumps(out["accuracy"]))
    Path("ml/results/gemini_tools.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
