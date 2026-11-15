# FinPilot — is it worth it?

**Veritas AI High School Hackathon 2026 · AI + Finance track**

> **This project is a prototype and is not financial advice.**

FinPilot is a family money copilot. Parents and teens share one **family room**: a shared view of
the family's money, upcoming bills, goals, and a personal space for each person. A **Chrome
extension** checks any product page (or a product and price you select) and answers
**Buy / Think about it / Not worth it** — with the reasons and a **reasonable price for you**.
*Concert tickets? Fine. Concert tickets for $100 this month? Not worth it: a reasonable price for
you this month is about $25.*

**One-line takeaway:** at the same number of warnings, FinPilot's verdict avoids
**$285 of overspending per family per month**, versus $201 for the popular 50/30/20 rule
(backtest on 4,033 real purchases from 83 families it never trained on).

---

## 1. The problem
- A family's money decisions are made one purchase at a time, in a shop, often by teens, while
  budgets live in spreadsheets nobody opens at checkout.
- Budget apps show what already happened. The decision that matters is the one *before* clicking Buy.
- Teens increasingly spend online with their own money, but they still depend on the family budget.

**Who it helps:** families with teens in the US (demo: the Carters — 2 parents, 2 teens).

## 2. What we built
| Part | What it does |
|---|---|
| **Family room** | Parent creates a room and gets an invite code (e.g. `CARTER-5626`). Everyone signs up with email + password and joins with the code. Parents and teens have different rights. |
| **Family overview** | Spending by category with an ML risk of ending the month over the usual level or the family's limit, who spent what, upcoming payments, family goals, 6-month trend. |
| **Upcoming** | Regular payments found by ML (rent, bills, subscriptions, loans) with next date and amount, plans the family adds by hand, and an ML forecast of what usually still goes out this month. |
| **My space** | Each member's allowance, own earnings, spending and personal goals. Teen spending also counts in the family totals. Parents set and pay allowance (recorded, or as PayPal Sandbox test money). |
| **Needs & wants setup** | After data arrives, ML suggests which categories are needs and which are wants (with regular payments as evidence); a parent confirms and sets monthly limits for wants. |
| **Add data** | PayPal Sandbox sync (payments go to the member whose PayPal email matches) and uploads read by **Gemini**: receipt photos, PDF statements, CSV/Excel tables. Our model categorizes each line; the user checks before importing. |
| **Product verdict** | Website page and Chrome extension: Buy / Think about it / Not worth it, reasons, reasonable price for you, market price range of similar items. |
| **Assistant** | One chat on the website and in the extension: spending, upcoming bills, goals, “can I buy…”, “where are we losing money”. An ML intent model picks the question type; every number is computed by code from the family's data. |

## 3. What we added ourselves (beyond calling an API)
- Five ML parts trained and tested by us, each against simple baselines and against Gemini.
- A verdict that combines the overspend forecast, the family's own usual prices, market prices and goals, under rules the team chose (see `docs/spec.md`).
- A **backtest of the decision itself** in dollars, not just model metrics.
- Learning from corrections: fixing one transaction re-labels every payment from that merchant and retrains the categorizer in the background.

## 4. How it works
```
PayPal Sandbox ─┐                                   ┌─ Website (family room)
Gemini uploads ─┼─► transactions (by member) ─► SQLite ─► FastAPI ─┤
Demo family    ─┘          │                         └─ Chrome extension (Bearer token)
                           ▼
   ML: 1 categories → need/want · 2 recurring payments · 3 overspend risk
       4 market price (our model + Gemini) · 5 verdict + reasonable price
       + intent model for the assistant
```
| # | Model | Data | Method |
|---|---|---|---|
| 1 | Categorization | Train: DoDataThings (68k synthetic bank lines). Test: Misata families (different generator) | TF-IDF (chars + words) + logistic regression; bank boilerplate removed; corrections weighted ×5 |
| 2 | Recurring payments | Misata labels of recurring streams | Series features (gaps, amount stability, coverage) + gradient boosting; next date from the usual gap |
| 3 | Overspend risk | Misata, 100 families × 24 months | Gradient boosting with a monotonic constraint (spending more never lowers risk), live features for any day |
| 4 | Market price | Amazon Products 2023 (80k products with prices) | Ridge regression on title TF-IDF + Gemini estimate, blend weight and range chosen on validation |
| 5 | Verdict | Outputs of 2–4 + family's usual prices + goals | Team rules; reasonable price = highest price keeping risk under the model's warning threshold |
| — | Assistant intent | 361 template phrases; 47 separately written test questions | TF-IDF + logistic regression |

## 5. Results (test data the models never saw)
**Overspend risk** (train 2025, threshold on Jan–Mar 2026, **test Apr–Sep 2026**, 17,030 cases):

| Method | Precision | Recall | PR-AUC |
|---|---|---|---|
| Proportion “spent × 30/day” | 0.686 | 0.676 | 0.754 |
| Pace “spent + what usually comes later” | 0.677 | 0.742 | 0.742 |
| **Our model** | **0.774** | **0.690** | **0.853** |

On day 5 of the month the model catches 55% of overspends (precision 62%) vs 45% (59%) for the proportion rule.

**Verdict backtest** — every online purchase ≥ $20 in Apr–Sep 2026 (4,033 purchases, 83 families), each method postpones the same number of purchases (17%):

| Method | $ overspend avoided / family / month | Precision | False alarms |
|---|---|---|---|
| 50/30/20 rule | $201 | 0.63 | 256 |
| Proportion rule | $232 | 0.82 | 126 |
| Overspend model alone | $286 | 0.99 | 4 |
| **FinPilot verdict** | **$285** | 0.66 | 236 |

**Recurring payments** (30% of families held out; history up to 2026-06-30):

| Method | Precision | Recall | F1 |
|---|---|---|---|
| “Same merchant 3+ times in 3+ months” | 0.165 | 0.895 | 0.278 |
| **Our model** | **0.956** | **0.976** | **0.966** |
| Gemini 3.5 Flash (100 series) | 0.75 | 1.00 | 0.857 (our model on the same 100: 0.917) |

Next payment within ±3 days: model 96% vs “last + 30 days” 84%.

**Market price** (7,277 products from stores the model never saw):

| Method | Median error | Within ±25% |
|---|---|---|
| Category median price | 54% | 24% |
| Our model | 37% | 36% |
| Gemini 3.5 Flash (100 products) | 26% | 46% |
| **Hybrid (used in the app)** | **26%** | **48%** |

**Categorization** (50 held-out families, 63,974 transactions, macro-F1): keywords 0.650 · **our model 0.692** · after 200 user corrections **0.836**. On 200 transactions, Gemini scores 0.833 vs our 0.646.

**Assistant intents** (47 questions, macro-F1): keywords 0.587 · **model 0.698**.

## 6. Where it fails (honest notes)
- **Synthetic data.** The family bank is synthetic (Misata); the teens' spending is generated by us. Real data is messier; recurring-payment scores are probably optimistic.
- **The “usual price” rule trades precision for dollars.** It flags expensive items even in months that end fine (e.g. a $1,458 Amazon order when the family still finished under budget), so the verdict's precision (0.66) is lower than the risk model alone (0.99). The backtest only counts overspending, not overpaying, so it cannot show the value of that rule.
- **Missed big purchases**: $542 on Amazon in a month that later tripled the usual level — the risk looked low (36%) mid-month.
- **Categorization mistakes**: credit-card interest read as “Entertainment”, Zelle money from a friend as “Income”, T-Mobile as “Transport”. The demo family has corrected two merchants; Gemini categorizes better than our small model.
- **Market prices are 2023 Amazon prices** and our model ignores brands (a Sony XM5 alone is estimated at ~$117); Gemini fixes most of this, so the hybrid leans on Gemini (weight 0.95).
- **Recurring false alarms**: credit-card autopay pairs and monthly interest charges look like bills.
- **Assistant**: “good morning” is read as “can I buy”, “how do we cut costs” as “goals”.
- Not covered by the backtest: market price and goal checks (bank lines have no product names; the dataset has no goals).

## 7. What's next
Real bank connections (open banking), parent approval of teen purchases, smarter allowance rules, a model trained on real (consented) family data, mobile app, more stores and currencies.

## 8. Run it
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python ml/data_prep.py            # downloads open data, builds tables
.venv/bin/uvicorn backend.main:app --port 8000
```
Open http://localhost:8000 → **Try the demo family** (Alex, Sam, Maya, Leo). Keys go in `.env`
(see `.env.example`): `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` (Sandbox), `GEMINI_API_KEY`.
Extension: see [extension/README.md](extension/README.md). Retrain everything: `notebooks/FinPilot_results.ipynb`.

## 9. Sources
**Data**
- Misata, *US Bank and Card Transactions (preview)*, CC BY 4.0 — https://huggingface.co/datasets/misatadata/us-bank-transactions
- DoDataThings, *US Bank Transaction Categories v2*, MIT — https://huggingface.co/datasets/DoDataThings/us-bank-transaction-categories-v2
- *Amazon Products 2023* (milistu), MIT, derived from McAuley Lab Amazon Reviews 2023 — https://huggingface.co/datasets/milistu/AMAZON-Products-2023
- PayPal Sandbox (test accounts) — https://developer.paypal.com

**Models and libraries:** scikit-learn (logistic regression, ridge, gradient boosting), pandas, NumPy, FastAPI, SQLite, Chart.js, Tailwind CSS.

**AI tools:** Google **Gemini 3.5 Flash** API (reads uploaded files, gives a price opinion, used as a baseline). **Claude (Anthropic)** was used as a coding assistant to help write and test the code; the team made the product decisions recorded in `docs/spec.md`.

**Team:** _[names, schools]_

> This project is a prototype and is not financial advice.
