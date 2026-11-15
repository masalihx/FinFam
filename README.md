# FinPilot — is it worth it?

**Veritas AI High School Hackathon 2026 · AI + Finance track**

> **This project is a prototype and is not financial advice.**

FinPilot is a family money advisor that lives **entirely inside a Chrome extension**, with **built-in ML
and no AI keys**. A family opens it with one shared **6-character password** (letters and digits). On
any product page FinPilot shows a short card: **Worth it / Think about it / Not worth it**, then how much
the family has left in that category this month, then the **average market price** of similar products
from our database. The side panel has exactly two parts: the **Advisor** and **Money** (where the family
writes expenses and income, or connects its own PayPal account with **Log in with PayPal**).

*Concert tickets? Fine. Concert tickets for $100 this month? Not worth it — the family has $57 left for
entertainment, the ML chance of overspending jumps from 20% to 100%, and a price that fits right now is about $16.*

**One-line takeaway:** at the same number of warnings, FinPilot's verdict avoids
**$285 of overspending per family per month**, versus $201 for the popular 50/30/20 rule
(backtest on 4,033 purchases from 83 families the models never saw).

---

## 1. The problem
- Money decisions happen one purchase at a time, in a shop — while the budget lives in a spreadsheet nobody opens at checkout.
- Budget apps show what already happened. The decision that matters is the one *before* clicking Buy.

**Who it helps:** US families (demo: the Carters — 2 parents, 2 teens).

## 2. What we built (all inside the extension)
| Part | What it does |
|---|---|
| **Family password** | Create a family → FinPilot suggests a 6-character password (or you choose one). Anyone in the family opens it with the same password. Only a salted hash is stored; each family sees only its own data. |
| **On-page card** | Turned on with the **Shop check** switch (side panel header, or right-click the FinPilot toolbar icon; the icon shows **ON**). Then on any product page (or a selected product + price, right-click **Is this worth it?**): verdict first → money left in the category this month and what the family usually spends by month end → ML risk forecast → average market price from our database → a price that fits now. **Postpone** saves it with a reminder. |
| **Advisor** | This month (spent, income, kept), ML advice cards (category likely to go over, bills due this week, what grew last month, goals behind), **Is it worth it?** for any item, **left to spend** per category with the ML risk, goals, and questions in plain English. **What can I buy?** answers with the largest amount per category that keeps our overspend model under its warning level; “Can I buy sneakers?” without a price uses the average price from our market database. |
| **Money** | Add an expense or income: the ML model picks the category while you type (you can change it). History with category fixes (one fix re-labels every payment from that merchant) and delete. **Connect PayPal**: the user logs in on PayPal's own page (Log in with PayPal, Sandbox); FinPilot gets their name and email and imports their payments made through our PayPal shop for the last 90 days. |

## 3. What we added ourselves (beyond calling an API)
- Six ML parts trained and tested by us, each against simple baselines (and against Gemini where we could).
- A **backtest of the decision itself** in dollars, not just model metrics.
- All models **exported from Python and ported to JavaScript**, verified number-for-number: **70 automated checks** in `extension/test.html` (incl. 1,536 verdict-rule cases and the market search).
- An **offline advisor**: our intent model + our money code answer questions; when the model is unsure it offers the next likely topics as buttons.

## 4. How it works
```
 Chrome extension (no server, no AI keys)
 ┌──── side panel ────┐            ┌── any shop page ──┐
 │ lock → Advisor │ Money│            │ detect.js + card  │
 └─────────┬──────────┘            └────────┬──────────┘
           │          background worker ◄───┘
           ▼                  ▼
   lib/ engine (same ES modules in both)
   ml.js       TF-IDF + logistic/ridge, gradient-boosted trees (from JSON)
   market.js   kNN search in 66k Amazon products (2023 prices)
   features.js live overspend features, recurring series
   finance.js  month summary, free cash, goals, upcoming bills
   verdict.js  decision rules + fitting price + short explanation
   assistant.js intent model → our tools
   store.js    family data in chrome.storage.local (password hash)
   paypal.js   Log in with PayPal (chrome.identity) + Transaction Search
```
| # | Model | Data | Method |
|---|---|---|---|
| 1 | Categorization | Train: DoDataThings (68k synthetic bank lines). Test: Misata families (different generator) | TF-IDF (chars + words) + logistic regression (compact: 28k features) |
| 2 | Recurring payments | Misata labels of recurring streams | Series features + gradient boosting; next date from the usual gap |
| 3 | Overspend risk | Misata, 100 families × 24 months | Gradient boosting, monotonic in spending, live features for any day of the month |
| 4 | Market price | Amazon Products 2023 (66k training products) | k nearest neighbours by title (TF-IDF cosine, k = 10): similarity-weighted median and 25–75% range |
| 5 | Verdict | Outputs of 2–4 + family's usual prices + goals + needs/wants | Team rules (`docs/spec.md`); fitting price = highest price keeping the risk under the model's warning threshold |
| 6 | Advisor topics | 992 template phrases (9 topics) | TF-IDF + logistic regression; unsure (p < 0.6) → 2 more topics as buttons. Answers are computed by models 2–5 |

## 5. Results (test data the models never saw)
**Overspend risk** (train 2025, threshold on Jan–Mar 2026, **test Apr–Sep 2026**, 17,030 cases):

| Method | Precision | Recall | PR-AUC |
|---|---|---|---|
| Proportion “spent × 30/day” | 0.686 | 0.676 | 0.754 |
| Pace “spent + what usually comes later” | 0.677 | 0.742 | 0.742 |
| **Our model** | **0.774** | **0.690** | **0.853** |

**Verdict backtest** — every online purchase ≥ $20 in Apr–Sep 2026 (4,033 purchases, 83 families); each method postpones the same share of purchases (17%):

| Method | $ overspend avoided / family / month | Precision | False alarms |
|---|---|---|---|
| 50/30/20 rule | $201 | 0.63 | 256 |
| Proportion rule | $232 | 0.82 | 126 |
| Overspend model alone | $286 | 0.99 | 4 |
| **FinPilot verdict** | **$285** | 0.66 | 236 |

**Verdict balance.** “Think about it” now judges the purchase, not the month: it needs the purchase itself to add 2+ points of overspend risk (or cross the warning level). Before, a category already likely to go over made almost everything “Think”. On 200 random Amazon items for the demo family (Shopping already at 85% risk): Worth it 1.5% → **36%**, Think 79.5% → **45%**, Not worth it 19% (unchanged). In the backtest “Think” fell from 21% to 10% of purchases; the headline numbers above count only “Not worth it” and did not change.

**Market price** (7,277 products from stores not in the training data; median error / share within ±25%):
category median 53.6% / 24% · ridge on titles 37.1% / 36% · **kNN search (used) 33.5% / 38%**.
For reference, Gemini estimated prices better (25.8% on 100 products) but needs an API key, so v4 does not use it.
The card shows a market price only when the listed price is within 3× of the similar items' range: that keeps 96% of
test products (error 32.7%); the hidden 4% had 88.6% error — mostly accessories with the same name.

**Recurring payments** (30% of families held out): rule “3+ times in 3+ months” F1 0.278 · **our model 0.966**.
Next payment within ±3 days: 96% vs 84% for “last + 30 days”.

**Categorization** (50 held-out families, macro-F1): keywords 0.650 · **compact model 0.696** · after 200 user corrections 0.836.

**Advisor topics** — model in the extension, before (v4.1) → after (v4.2: new skill “What can I buy?”, 992 instead of 612 training phrases):

| Test (written before the change, never trained on) | Keywords | v4.1 model | **v4.2 model** | v4.2: right answer or right button |
|---|---|---|---|---|
| 40 new questions | 37.5% | 60% | **77.5%** | **87.5%** (was 75%) |
| 20 fresh questions | 30% | 60% | **65%** | 75% (was 75%) |

`ml/train_intent.py` refuses to train if a test question is in the training phrases, or nearly copied (character similarity ≥ 0.95); two pairs are close but were in the training data before the tests were written (“thank you” / “thank you so much”, 0.90). The older 47-question set overlaps the added phrases, so we no longer report it.

## 6. Where it fails (honest notes)
- **Synthetic data.** The family bank is synthetic (Misata); the teens' spending is generated by us. Recurring-payment scores are probably optimistic.
- **Market price by title can be fooled.** *Sony WH-1000XM5* at $348: the database has the exact model ($398) and the XM4 ($348), but cheaper Sony headphones among the 10 neighbours pull the average to $98 ("255% above"). *AirPods Pro* at $249: the nearest titles are $10 cases, so the 3× rule hides the market price. Sharper similarity weights did not help on validation (34.2% → 34.6–40%). Prices are from 2023.
- **Advisor still misses 1 in 4–5 free-text questions** (77.5% / 65%): “which category is most at risk” → where we lose money, “howdy” → spending, “anything I parked for later?” → is it worth it. The advisor shows how it understood each question and offers the next topics as buttons. A small language model could understand more, but strong ones are far too big for an extension.
- **The “usual price” rule trades precision for dollars**: it flags expensive items even in months that end fine.
- **Missed big purchases**: $542 on Amazon mid-month looked low-risk (36%); the month later tripled.
- **Categorization mistakes**: credit-card interest read as Entertainment, T-Mobile as Transport — fixable with one click, and the fix spreads to the same merchant. A $1,200 PayPal "Salary" was read as Shopping (and counted as negative spending); now money that surely came in (PayPal receipts, entries marked Income) counts as income. We do not apply this to bank lines: there many shopping refunds are positive, and a general rule lowered test macro-F1 (0.6961 → 0.6953).
- **One computer**: the family's data lives in one browser; syncing across devices needs a server (next step).
- **PayPal shows only part of a person's spending.** PayPal gives third-party apps the person's name and email, not their whole payment history, so FinPilot imports only payments made through our PayPal shop (Sandbox, test money). Full history would need a bank-data aggregator (paid) or PayPal partner approval. Our app's PayPal secret sits in the extension because there is no server; a real product would exchange the login code on a server.

## 7. What's next
Family sync across devices, real bank connections (open banking), fresher price data, parent approval of teen purchases, a model trained on real (consented) family data.

## 8. Install and run
1. Download this repository (Code → Download ZIP) and unzip, or `git clone`.
2. Chrome → `chrome://extensions` → switch on **Developer mode** → **Load unpacked** → choose the `extension/` folder.
3. Click the FinPilot icon → the side panel opens → **Try the demo family** (password **DEMO26**) or **Create a new family**.
4. Optional: **Money → Connect PayPal → Log in with PayPal** and log in with a PayPal **Sandbox personal** account. (Developers: this needs `extension/paypal.config.json`, made from `.env` by `python3 scripts/make_paypal_config.py`, and in the Sandbox app: *Log in with PayPal* on, Return URL `https://lakkaedhdeopfgfnpioemhplfomfgbam.chromiumapp.org/paypal`, *Transaction Search* on.)
5. Turn on **Shop check** (switch at the top of the panel, or right-click the FinPilot icon). Open any product page (e.g. Amazon) — the card appears; or select a product and price → right-click → **Is this worth it?**

Engine tests: serve `extension/` over http (`python3 -m http.server`) and open `test.html?memory` (70 checks) or `card-test.html?memory` (the card on a test product page).
Retrain and re-export the models: `pip install -r requirements.txt`, then `python ml/data_prep.py`, the `ml/train_*.py` scripts, and `python ml/export_extension.py`. Results notebook: `notebooks/FinPilot_results.ipynb`. Earlier versions are kept: website v2 in `backend/` and `web/`.

## 9. Sources
**Data**
- Misata, *US Bank and Card Transactions (preview)*, CC BY 4.0 — https://huggingface.co/datasets/misatadata/us-bank-transactions
- DoDataThings, *US Bank Transaction Categories v2*, MIT — https://huggingface.co/datasets/DoDataThings/us-bank-transaction-categories-v2
- *Amazon Products 2023* (milistu), MIT, derived from McAuley Lab Amazon Reviews 2023 — https://huggingface.co/datasets/milistu/AMAZON-Products-2023
- PayPal Sandbox (test accounts) — https://developer.paypal.com

**Models and libraries:** scikit-learn (logistic regression, ridge, gradient boosting, TF-IDF), pandas, NumPy; the extension uses plain JavaScript (no external libraries).

**AI tools:** Google **Gemini** API (`gemini-3.5-flash`, `gemini-3.5-flash-lite`) was used **only as an evaluation baseline** (categorization, recurring payments, prices, assistant tool choice in v3); the v4 extension does not call it. **Claude (Anthropic)** was used as a coding assistant to help write and test the code; the team made the product decisions recorded in `docs/spec.md`.

**Team:** _[names, schools]_

> This project is a prototype and is not financial advice.
