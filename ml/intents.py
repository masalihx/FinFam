"""Assistant intents: training phrases, a separate test set, and a keyword baseline.

Training phrases are generated from templates. The test questions were written
separately, in different words, so the score shows how well the model handles
phrasings it has not seen. (The team should add its own questions to TEST_QUESTIONS.)
"""
import itertools
import random
import re

INTENTS = ["spending", "can_afford", "can_spend", "budget_left", "goals", "where_losing", "postponed", "upcoming", "help"]

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
        "how much is left for {cat}", "will i overspend on {cat}",
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

# Written on Nov 15 BEFORE the v4.2 retraining (new skill "can_spend": what can I buy / how much can I spend).
# Never used for training; train_intent.py asserts none of these appear in the training phrases.
NEW_TEST_QUESTIONS = [
    ("what was our total spending in october", "spending"),
    ("how much did the kids stuff cost us this month", "spending"),
    ("breakdown of where our money went last month", "spending"),
    ("how much did we pay for gas recently", "spending"),
    ("did we spend a lot on eating out", "spending"),
    ("is a $60 hoodie a good buy right now", "can_afford"),
    ("thinking of getting airpods for 249, good idea?", "can_afford"),
    ("would a $1,500 laptop break our budget", "can_afford"),
    ("should we book a weekend trip for 400 dollars", "can_afford"),
    ("worth it to buy a $30 video game?", "can_afford"),
    ("what can i buy", "can_spend"),
    ("how much can i spend this week without problems", "can_spend"),
    ("what's safe to spend on clothes right now", "can_spend"),
    ("do we have room for something fun this month", "can_spend"),
    ("how much could i spend on a gift", "can_spend"),
    ("what's my spending money", "can_spend"),
    ("how close are we to going over on dining", "budget_left"),
    ("are groceries under control this month", "budget_left"),
    ("how much is still available in the shopping budget", "budget_left"),
    ("are we going to make it to the end of the month", "budget_left"),
    ("which category is most at risk", "budget_left"),
    ("anything big due next week?", "upcoming"),
    ("when is the next netflix charge", "upcoming"),
    ("list our recurring payments", "upcoming"),
    ("what will leave our account soon", "upcoming"),
    ("can we still afford the car by next year", "goals"),
    ("progress on saving for college", "goals"),
    ("how many months until we reach our savings target", "goals"),
    ("are our goals realistic", "goals"),
    ("where can we save money", "where_losing"),
    ("which subscriptions should we cancel", "where_losing"),
    ("what spending looks unusual", "where_losing"),
    ("biggest waste of money lately", "where_losing"),
    ("show the stuff i decided not to buy yet", "postponed"),
    ("anything i parked for later?", "postponed"),
    ("remind me what i put on hold", "postponed"),
    ("howdy", "help"),
    ("what kind of questions can i ask", "help"),
    ("are you a bot", "help"),
    ("thank you so much", "help"),
]

KEYWORDS = [
    ("upcoming", ["upcoming", "due", "coming up", "renew", "bills"]),
    ("postponed", ["postpone", "wait list", "waiting", "delay"]),
    ("goals", ["goal", "college", "fund", "save for", "target"]),
    ("where_losing", ["losing", "cut", "save more", "leak", "overspending on", "biggest", "spend less"]),
    ("budget_left", ["left", "budget", "over budget", "overspend", "on track", "limit"]),
    ("can_spend", ["what can i buy", "safe to spend", "can i spend", "spending money"]),
    ("can_afford", ["can i buy", "afford", "should i buy", "should i get", "buy"]),
    ("spending", ["spend", "spent", "expenses", "cost"]),
    ("help", ["hi", "hello", "help", "thanks", "what can you do"]),
]


# Added on Nov 15 for the built-in advisor (no Gemini): more varied wording per intent.
# Some phrases overlap the old 47 test questions, so FRESH_TEST_QUESTIONS is the honest test after this change.
EXTRA_TEMPLATES = {'spending': ['what did {cat} cost us {month}', '{cat} total {month}', 'how much went to {cat}', 'sum of {cat} payments', '{cat} bill total', 'money spent on {cat} {month}', 'show {cat} costs', 'what have we paid for {cat}'], 'can_afford': ['thinking about {item} for {price}', 'would buying {item} hurt us', 'is it a good idea to buy {item}', 'can our family pay for {item}', 'worth buying {item} for {price}', 'should i order {item} now', '{item} costs {price}, should i'], 'budget_left': ['are we spending too fast {month}', 'is the {cat} budget ok', 'chance of going over on {cat}', 'remaining money for {cat}', 'are we near the {cat} budget'], 'goals': ['are we behind on saving', 'update on our targets', 'how far along is {goal}', 'is {goal} on schedule', 'how much is saved for {goal}'], 'where_losing': ['how do we cut costs', 'any ideas to save', 'what is wasting our money', 'which category grew the most', 'help me spend less'], 'postponed': ['things i put off buying', 'my delayed purchases', 'how much did waiting save us', 'items i decided to wait on'], 'upcoming': ['what do we owe soon', 'charges coming up {month}', 'payments due in the next two weeks', 'calendar of payments', 'which bills hit the account soon'], 'help': ['good morning', 'can you explain what you do', 'ok thanks a lot', 'what are you', 'hello there']}
for _intent, _templates in EXTRA_TEMPLATES.items():
    TEMPLATES[_intent] = TEMPLATES[_intent] + _templates


# Added on Nov 15 (v4.2, after NEW_TEST_QUESTIONS were frozen): the new skill "can_spend" and more general wording.
# Written to cover common phrasings, not the test questions; train_intent.py rejects exact and near-duplicates.
V42_TEMPLATES = {
    "can_spend": ["what can i afford {month}", "what can i still buy {month}", "how much is safe to spend on {cat}",
                  "how much money can i spend now", "how much can i still spend on {cat} {month}", "free money left {month}",
                  "spending allowance for {cat}", "what is ok to buy right now", "how much can i put toward {item}",
                  "max i should spend on {item}", "safe amount to spend {month}", "what can we buy without going over",
                  "how much extra can we spend {month}", "could i treat myself {month}", "what purchase fits our budget",
                  "can we still spend on {cat}", "how much do i have for fun {month}", "budget for {item}"],
    "spending": ["how much have we spent so far {month}", "total expenses {month}", "spending summary {month}",
                 "what were our costs {month}", "how much did {cat} come to", "amount spent on {cat} {month}",
                 "expenses by category {month}", "how expensive was {cat} {month}"],
    "can_afford": ["can i get {item}", "is buying {item} ok {month}", "{item} for {price} yes or no",
                   "should we spend {price} on {item}", "is {item} worth it", "would {price} be too much for {item}",
                   "can we buy {item} this week", "verdict on {item} for {price}", "do we have enough for {item}"],
    "budget_left": ["how is {cat} looking {month}", "are we over on {cat}", "budget status {month}",
                    "how much of the {cat} budget is used", "will {cat} go over", "overspending risk {month}",
                    "are we ok on {cat}", "budget health {month}"],
    "upcoming": ["next payments", "what is charged next {month}", "bills this week", "when do we pay for {cat}",
                 "what renews {month}", "upcoming charges for {cat}", "money going out soon"],
    "goals": ["goal progress", "how is saving going", "when do we hit {goal}", "can we reach {goal}",
              "savings plan for {goal}", "how much is left to save for {goal}"],
    "where_losing": ["where do we overspend", "what costs too much", "unnecessary expenses", "how to spend less on {cat}",
                     "what can we cut back on", "spending that grew {month}"],
    "postponed": ["deferred purchases", "what am i waiting to buy", "saved by postponing", "list of things i skipped"],
    "help": ["what do you do", "how do i use this", "thanks a lot", "cheers", "hello finpilot"],
}
TEMPLATES.setdefault("can_spend", [])
for _intent, _templates in V42_TEMPLATES.items():
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
