"""Tool declarations and the teaching context for the Gemini assistant (shared by the extension and the evaluation).

    .venv/bin/python ml/export_assistant_spec.py
"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from categories import CATEGORIES  # noqa: E402
from intents import TEMPLATES  # noqa: E402

INTENT_TOOL = {"spending": "get_spending", "can_afford": "check_purchase", "budget_left": "get_month_summary",
               "goals": "get_goals", "where_losing": "where_losing_money", "postponed": "get_postponed",
               "upcoming": "get_upcoming", "help": None}

TOOLS = [
    {"name": "get_month_summary", "description": "This month's spending, income, money kept per month, and for each category: spent, usual level or family limit, ML chance of going over, expected rest of month.",
     "parameters": {"type": "OBJECT", "properties": {}}},
    {"name": "get_spending", "description": "Total spending by category and by person for a month (past months too).",
     "parameters": {"type": "OBJECT", "properties": {
         "category": {"type": "STRING", "enum": CATEGORIES, "description": "Only this category"},
         "month": {"type": "STRING", "description": "Month as YYYY-MM; default this month"},
         "scope": {"type": "STRING", "enum": ["family", "me"], "description": "'me' for the person asking (e.g. a teen asking about their own money)"}}}},
    {"name": "get_upcoming", "description": "Regular payments found by the ML model (rent, bills, subscriptions) and planned expenses for the next days.",
     "parameters": {"type": "OBJECT", "properties": {"days": {"type": "INTEGER", "description": "How many days ahead, default 30"}}}},
    {"name": "get_goals", "description": "Family goals and the asker's personal goals: needed per month, projected date, on track or behind.",
     "parameters": {"type": "OBJECT", "properties": {}}},
    {"name": "check_purchase", "description": "FinPilot's ML verdict for buying something now: Buy / Think about it / Not worth it, reasons, reasonable price for the family, market price range.",
     "parameters": {"type": "OBJECT", "properties": {"title": {"type": "STRING"}, "price": {"type": "NUMBER"}, "url": {"type": "STRING"}},
                    "required": ["title", "price"]}},
    {"name": "where_losing_money", "description": "Categories that grew most compared with a usual month, share of income spent on wants, yearly cost of subscriptions.",
     "parameters": {"type": "OBJECT", "properties": {}}},
    {"name": "get_postponed", "description": "Purchases the family postponed and money kept by not buying.",
     "parameters": {"type": "OBJECT", "properties": {}}},
]

random.seed(7)
examples = []
for intent, templates in TEMPLATES.items():
    for t in random.sample(templates, 2):
        text = t.format(cat="dining", month="last month", item="a jacket", price="$120", goal="the college fund")
        examples.append({"q": " ".join(text.split()), "tool": INTENT_TOOL[intent]})

INSTRUCTION = """You are FinPilot, a family money assistant inside a Chrome extension. Today is {today}.
Family: {family}. You are talking to {me}.
Needs and wants set by the parents: {needs_wants}.

Rules:
- Never calculate or guess money numbers yourself. Always call a tool and use only the numbers it returns.
- Pick the tool by the question type. Examples (question -> tool):
{examples}
- For greetings, thanks or "what can you do", answer in one or two sentences without tools.
- If a teen asks about "my" money, use scope "me".
- Answer in short, plain English (at most 5 short lines). Say "this is not financial advice" only when giving a recommendation.
- Category names: {categories}."""

spec = {"tools": TOOLS, "instruction": INSTRUCTION, "examples": examples, "intent_tool": INTENT_TOOL}
Path("extension/data/assistant_spec.json").write_text(json.dumps(spec, indent=1))
print(f"{len(TOOLS)} tools, {len(examples)} examples")
