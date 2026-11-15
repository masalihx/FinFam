"""Assistant intents: training phrases, a separate test set, and a keyword baseline.

Training phrases are generated from templates. The test questions were written
separately, in different words, so the score shows how well the model handles
phrasings it has not seen. (The team should add its own questions to TEST_QUESTIONS.)
"""
import itertools
import random
import re

INTENTS = ["spending", "can_afford", "budget_left", "goals", "where_losing", "postponed", "upcoming", "help"]

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
    "upcoming": [
        "what bills are coming up", "upcoming payments", "what do we have to pay {month}", "when is rent due",
        "what payments are due soon", "show upcoming expenses", "any bills next week", "what will be charged soon",
        "list our regular payments", "what subscriptions renew soon", "what is due before payday",
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
    ("which charges are about to hit our account", "upcoming"),
    ("is the phone bill due soon", "upcoming"),
    ("what do we owe in the next two weeks", "upcoming"),
    ("calendar of payments for this month", "upcoming"),
    ("good morning", "help"),
    ("what are you", "help"),
    ("can you explain what you do", "help"),
    ("ok thanks a lot", "help"),
]

# Written on Nov 15 before adding the extra training phrases below; never used for training or tuning.
FRESH_TEST_QUESTIONS = [
    ("how much has gone on takeout so far", "spending"),
    ("total for gas in october", "spending"),
    ("what was our biggest expense this month", "spending"),
    ("is $45 for a hoodie ok", "can_afford"),
    ("should we get a $700 couch", "can_afford"),
    ("i want new airpods for 179 dollars", "can_afford"),
    ("how close are we to the grocery limit", "budget_left"),
    ("do we still have money for eating out this month", "budget_left"),
    ("will dining go over", "budget_left"),
    ("when do we finish saving for the car", "goals"),
    ("how much should we put away monthly for college", "goals"),
    ("what can we stop paying for", "where_losing"),
    ("which spending went up compared to normal", "where_losing"),
    ("show what i'm waiting to buy", "postponed"),
    ("what's on hold", "postponed"),
    ("next bills", "upcoming"),
    ("which subscriptions charge us next week", "upcoming"),
    ("rent date", "upcoming"),
    ("much appreciated", "help"),
    ("what is finpilot", "help"),
]

KEYWORDS = [
    ("upcoming", ["upcoming", "due", "coming up", "renew", "bills"]),
    ("postponed", ["postpone", "wait list", "waiting", "delay"]),
    ("goals", ["goal", "college", "fund", "save for", "target"]),
    ("where_losing", ["losing", "cut", "save more", "leak", "overspending on", "biggest", "spend less"]),
    ("budget_left", ["left", "budget", "over budget", "overspend", "on track", "limit"]),
    ("can_afford", ["can i buy", "afford", "should i buy", "should i get", "buy"]),
    ("spending", ["spend", "spent", "expenses", "cost"]),
    ("help", ["hi", "hello", "help", "thanks", "what can you do"]),
]


# Added on Nov 15 for the built-in advisor (no Gemini): more varied wording per intent.
# Some phrases overlap the old 47 test questions, so FRESH_TEST_QUESTIONS is the honest test after this change.
EXTRA_TEMPLATES = {'spending': ['what did {cat} cost us {month}', '{cat} total {month}', 'how much went to {cat}', 'sum of {cat} payments', '{cat} bill total', 'money spent on {cat} {month}', 'show {cat} costs', 'what have we paid for {cat}'], 'can_afford': ['thinking about {item} for {price}', 'would buying {item} hurt us', 'is it a good idea to buy {item}', 'can our family pay for {item}', 'worth buying {item} for {price}', 'should i order {item} now', '{item} costs {price}, should i'], 'budget_left': ['are we spending too fast {month}', 'is the {cat} budget ok', 'chance of going over on {cat}', 'remaining money for {cat}', 'can we still spend on {cat}', 'are we near the {cat} budget'], 'goals': ['are we behind on saving', 'update on our targets', 'how far along is {goal}', 'is {goal} on schedule', 'how much is saved for {goal}'], 'where_losing': ['how do we cut costs', 'any ideas to save', 'what is wasting our money', 'which category grew the most', 'help me spend less'], 'postponed': ['things i put off buying', 'my delayed purchases', 'how much did waiting save us', 'items i decided to wait on'], 'upcoming': ['what do we owe soon', 'charges coming up {month}', 'payments due in the next two weeks', 'calendar of payments', 'which bills hit the account soon'], 'help': ['good morning', 'can you explain what you do', 'ok thanks a lot', 'what are you', 'hello there']}
for _intent, _templates in EXTRA_TEMPLATES.items():
    TEMPLATES[_intent] = TEMPLATES[_intent] + _templates


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
