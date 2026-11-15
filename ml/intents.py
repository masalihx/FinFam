"""Assistant intents: training phrases, a separate test set, and a keyword baseline.

Training phrases are generated from templates. The test questions were written
separately, in different words, so the score shows how well the model handles
phrasings it has not seen. (The team should add its own questions to TEST_QUESTIONS.)
"""
import itertools
import random
import re

INTENTS = ["spending", "can_afford", "budget_left", "goals", "where_losing", "postponed", "help"]

CATS = ["dining", "restaurants", "coffee", "groceries", "food", "shopping", "clothes", "amazon", "gas",
        "transport", "uber", "movies", "entertainment", "subscriptions", "netflix", "travel", "health",
        "pharmacy", "haircuts", "rent", "bills", "utilities"]
MONTHS = ["", "this month", "last month", "in october", "in september", "in august", "this year"]
ITEMS = ["a jacket", "new headphones", "a laptop", "sneakers", "a tv", "a phone", "concert tickets",
         "a gaming console", "a dress", "a bike", "this", "it"]
PRICES = ["$50", "$120", "$200", "$348", "$999", "80 dollars", "$1,200", "300 bucks"]
GOALS = ["college fund", "the car", "our goals", "my savings goal", "the house"]

TEMPLATES = {
    "spending": [
        "how much did i spend on {cat} {month}", "how much did we spend on {cat}", "what did i spend on {cat} {month}",
        "total spent on {cat} {month}", "show my {cat} spending", "how much money went to {cat} {month}",
        "my {cat} expenses {month}", "how much have we spent {month}", "what are my expenses {month}",
        "spending on {cat}", "how much on {cat} {month}",
    ],
    "can_afford": [
        "can i buy {item} for {price}", "can i afford {item}", "should i buy {item} for {price}",
        "is it ok to spend {price} on {item}", "can we afford {price}", "should i get {item}",
        "is {price} for {item} too much right now", "buy {item} now or wait", "can i spend {price} today",
        "do i have money for {item}", "is it a good time to buy {item}",
    ],
    "budget_left": [
        "how much is left for {cat}", "how much can i still spend on {cat} {month}", "will i overspend on {cat}",
        "am i over budget on {cat}", "what is my {cat} budget", "how much room is left in {cat}",
        "am i on track this month", "will i go over budget this month", "how is my budget",
        "what's left to spend {month}", "risk of overspending on {cat}",
    ],
    "goals": [
        "how are my goals", "when will we reach {goal}", "are we on track for {goal}", "how much should we save for {goal}",
        "progress on {goal}", "how long until {goal}", "how much do i need to save each month",
        "will we make it to {goal} on time", "what about {goal}", "savings goals status",
    ],
    "where_losing": [
        "where am i losing money", "where does my money go", "what can i cut", "how can i save more",
        "where can we save", "what am i overspending on", "biggest expenses", "tips to save money",
        "what should i spend less on", "why is my spending so high {month}", "where is the money leaking",
    ],
    "postponed": [
        "what did i postpone", "show postponed purchases", "how much did i save by waiting",
        "what is on my wait list", "remind me what i postponed", "postponed items",
        "what purchases did i delay", "how much money is waiting", "list my postponed things",
    ],
    "help": [
        "hi", "hello", "what can you do", "help", "who are you", "how does this work", "thanks", "thank you",
        "what can i ask", "hey there",
    ],
}

# Written separately from the templates, in different words.
TEST_QUESTIONS = [
    ("what did eating out cost us last month?", "spending"),
    ("restaurant bill total for october", "spending"),
    ("how much went on groceries recently", "spending"),
    ("tell me my uber costs", "spending"),
    ("money spent on netflix and stuff", "spending"),
    ("our entertainment costs in september", "spending"),
    ("sum of my clothing purchases", "spending"),
    ("how big were our bills this month", "spending"),
    ("is a $250 coat affordable right now", "can_afford"),
    ("thinking about a $600 ipad, good idea?", "can_afford"),
    ("may i purchase sneakers for 90 dollars", "can_afford"),
    ("would buying a new phone hurt us", "can_afford"),
    ("can my family pay for a $1500 vacation", "can_afford"),
    ("should i order this now", "can_afford"),
    ("is now a bad time for a big purchase", "can_afford"),
    ("worth buying a drone for $400?", "can_afford"),
    ("how much shopping money do i have left", "budget_left"),
    ("are we going to blow the grocery budget", "budget_left"),
    ("is my dining budget ok", "budget_left"),
    ("remaining budget for transport", "budget_left"),
    ("are we spending too fast this month", "budget_left"),
    ("chance i go over on entertainment", "budget_left"),
    ("how close am i to my limit for shopping", "budget_left"),
    ("is the college fund on schedule", "goals"),
    ("when do we get the new car", "goals"),
    ("monthly amount needed for our savings targets", "goals"),
    ("are we behind on saving", "goals"),
    ("how far along is the house fund", "goals"),
    ("update me on my targets", "goals"),
    ("what's eating my budget", "where_losing"),
    ("help me spend less", "where_losing"),
    ("which category grew the most", "where_losing"),
    ("how do we cut costs", "where_losing"),
    ("any ideas to save", "where_losing"),
    ("what is wasting our money", "where_losing"),
    ("which items am i waiting to buy", "postponed"),
    ("things i put off buying", "postponed"),
    ("how much have i not spent thanks to waiting", "postponed"),
    ("my delayed purchases list", "postponed"),
    ("good morning", "help"),
    ("what are you", "help"),
    ("can you explain what you do", "help"),
    ("ok thanks a lot", "help"),
]

KEYWORDS = [
    ("postponed", ["postpone", "wait list", "waiting", "delay"]),
    ("goals", ["goal", "college", "fund", "save for", "target"]),
    ("where_losing", ["losing", "cut", "save more", "leak", "overspending on", "biggest", "spend less"]),
    ("budget_left", ["left", "budget", "over budget", "overspend", "on track", "limit"]),
    ("can_afford", ["can i buy", "afford", "should i buy", "should i get", "buy"]),
    ("spending", ["spend", "spent", "expenses", "cost"]),
    ("help", ["hi", "hello", "help", "thanks", "what can you do"]),
]


def keyword_intent(text: str) -> str:
    low = text.lower()
    for intent, words in KEYWORDS:
        if any(re.search(r"\b" + re.escape(w), low) for w in words):
            return intent
    return "help"


def training_phrases(seed: int = 0, per_template: int = 12):
    rng = random.Random(seed)
    rows = []
    for intent, templates in TEMPLATES.items():
        for t in templates:
            combos = list(itertools.product(CATS, MONTHS, ITEMS, PRICES, GOALS))
            for cat, month, item, price, goal in rng.sample(combos, per_template):
                text = t.format(cat=cat, month=month, item=item, price=price, goal=goal)
                rows.append((re.sub(r"\s+", " ", text).strip(), intent))
    return sorted(set(rows))
