# FinPilot — is it worth it?

**Veritas AI High School Hackathon 2026 · AI + Finance track**

> **This project is a prototype and is not financial advice.**

FinPilot is a family money copilot that lives **entirely inside a Chrome extension**. Parents and teens
each have a profile (with a PIN) in the family's FinPilot. A **side panel** shows the family's month,
upcoming bills, goals and each person's own space. On any product page — or a product and price you
select — FinPilot answers **Buy / Think about it / Not worth it**, with the reasons and a
**reasonable price for you**. *Concert tickets? Fine. Concert tickets for $100 this month? Not worth it —
a reasonable price for this family right now is about $16.*

Our own ML models run **inside the browser** (exported from Python, checked number-for-number). Gemini
only explains, chats and reads uploaded receipts; it is "taught" through context and calls our models
as tools. No server: the family's data never leaves the computer except to Gemini/PayPal when used.

**One-line takeaway:** at the same number of warnings, FinPilot's verdict avoids
**$285 of overspending per family per month**, versus $201 for the popular 50/30/20 rule
(backtest on 4,033 real purchases from 83 families the models never saw).

---

## 1. The problem
- Money decisions happen one purchase at a time, in a shop, often by a teen with a phone — while the budget lives in a spreadsheet nobody opens at checkout.
- Budget apps show what already happened. The decision that matters is the one *before* clicking Buy.
- Teens spend online with their own money but still depend on the family budget.

**Who it helps:** US families with teens (demo: the Carters — 2 parents, 2 teens).

## 2. What we built (all inside the extension)
| Part | What it does |
|---|---|
| **Family profiles** | First run: create the family (members, roles, 4-digit PINs) or load the demo. Parents and teens have different rights (only parents change family goals, limits and allowance). |
| **Home** | This month by category with the **ML risk of going over** the usual level or the family's limit, who spent what (teens count in the total), upcoming payments, family goals. |
| **Upcoming** | Regular payments **found by ML** (rent, bills, subscriptions) with next date and amount, plans added by hand, and what usually still goes out this month. |
| **Me** | Each person's allowance, earnings, cash spending and personal goals; parents set and pay allowance. |
| **Needs & wants** | ML suggests needs vs wants (with regular payments as evidence); a parent confirms and sets limits for wants. Verdicts use this. |
| **Add data** | Receipt photo / PDF statement / CSV → **Gemini** reads it → our model categorizes each line → you check and import. PayPal Sandbox sync (payments go to the member whose PayPal email matches). |
| **Verdict** | On-page card and Check tab: Buy / Think about it / Not worth it, reasons, reasonable price, market price range of similar items. |
| **Ask** | One assistant in the panel and on the card. Gemini + our tools; offline it falls back to our intent model. |

## 3. What we added ourselves (beyond calling an API)
- Five ML parts trained and tested by us, each against simple baselines and against Gemini.
- A **backtest of the decision itself** in dollars, not just model metrics.
- The models **ported to JavaScript** and verified against Python (41 automated checks, incl. 672 verdict-rule cases) so the extension runs them offline.
- Gemini **taught through context** (family rules, needs & wants, examples from our intent dataset) with our models as tools — and measured: see 5.
- Learning from corrections: fixing one transaction re-labels every payment from that merchant.

## 4. How it works
```
 Chrome extension (no server)
 ┌──────────────── side panel ────────────────┐   ┌── any shop page ──┐
 │ Home · Upcoming · Ask · Me · More           │   │ content script    │
 └──────────────┬─────────────────────────────┘   └────────┬──────────┘
                │                 background worker ◄──────┘
                ▼                         ▼
   lib/ engine (ES modules, same code in both)
   ml.js        TF-IDF + logistic/ridge, gradient-boosted trees (from JSON)
   features.js  live overspend features, recurring series
   finance.js   month summary, free cash, goals, needs/wants
   verdict.js   decision rules + reasonable price + market price
   assistant.js Gemini with our tools · offline intent model
   store.js     family data in chrome.storage.local (profiles, PIN hashes)
```
| # | Model | Data | Method |
|---|---|---|---|
| 1 | Categorization | Train: DoDataThings (68k synthetic bank lines). Test: Misata families (different generator) | TF-IDF (chars + words) + logistic regression (compact: 28k features) |
| 2 | Recurring payments | Misata labels of recurring streams | Series features + gradient boosting (300 trees); next date from the usual gap |
| 3 | Overspend risk | Misata, 100 families × 24 months | Gradient boosting (400 trees), monotonic in spending, live features for any day |
| 4 | Market price | Amazon Products 2023 (80k products with prices) | Ridge on title TF-IDF (compact: 40k features) blended with a Gemini estimate (weight chosen on validation) |
| 5 | Verdict | Outputs of 2–4 + family's usual prices + goals + needs/wants | Team rules (`docs/spec.md`); reasonable price = highest price keeping risk under the model's warning threshold |
| — | Assistant | 361 template phrases; 47 separately written test questions | Gemini + context + our tools; offline: TF-IDF + logistic regression intent model |

## 5. Results (test data the models never saw)
**Overspend risk** (train 2025, threshold on Jan–Mar 2026, **test Apr–Sep 2026**, 17,030 cases):

| Method | Precision | Recall | PR-AUC |
|---|---|---|---|
| Proportion “spent × 30/day” | 0.686 | 0.676 | 0.754 |
| Pace “spent + what usually comes later” | 0.677 | 0.742 | 0.742 |
| **Our model** | **0.774** | **0.690** | **0.853** |

On day 5 of the month the model catches 55% of overspends (precision 62%) vs 45% (59%) for the proportion rule.

**Verdict backtest** — every online purchase ≥ $20 in Apr–Sep 2026 (4,033 purchases, 83 families); each method postpones the same number of purchases (17%):

| Method | $ overspend avoided / family / month | Precision | False alarms |
|---|---|---|---|
| 50/30/20 rule | $201 | 0.63 | 256 |
| Proportion rule | $232 | 0.82 | 126 |
| Overspend model alone | $286 | 0.99 | 4 |
| **FinPilot verdict** | **$285** | 0.66 | 236 |

**Recurring payments** (30% of families held out): rule “3+ times in 3+ months” F1 0.278 · **our model 0.966** · Gemini on 100 series 0.857 (our model on the same 100: 0.917). Next payment within ±3 days: 96% vs 84% for “last + 30 days”.

**Market price** (7,277 products from unseen stores; median error / within ±25%): category median 54% / 24% · our compact model 38% / 35% · Gemini 26% / 46% · **hybrid 26% / 48%**.

**Categorization** (50 held-out families, macro-F1): keywords 0.650 · **compact model 0.696** · after 200 user corrections 0.836 (full model). Gemini on 200 lines: 0.833 vs our 0.646.

**Assistant — does teaching Gemini through context help?** (47 separately written questions, correct tool chosen):
| Method | Correct tool |
|---|---|
| Our intent model (offline fallback, keywords baseline 0.55) | 72% |
| Gemini 3.5 Flash-Lite + our tools, no teaching context | 89% |
| **Gemini + our teaching context + our tools (used in FinPilot)** | **91.5%** |

Teaching helps only a little (one question out of 47 — honest result); most of the gain comes from giving Gemini our tools at all. Remaining misses: “money spent on netflix and stuff” → upcoming bills instead of spending; “should I order this now” without a price → no tool.

**JS port = Python:** 41/41 automated checks in `extension/test.html` (models, live features, money math, store rights, 672 verdict cases).

## 6. Where it fails (honest notes)
- **Synthetic data.** The family bank is synthetic (Misata); the teens' spending is generated by us. Recurring-payment scores are probably optimistic.
- **The “usual price” rule trades precision for dollars**: it flags expensive items even in months that end fine (a $1,458 Amazon order in a month that finished under budget). The backtest counts overspending, not overpaying, so it can't show that rule's value.
- **Missed big purchases**: $542 on Amazon mid-month looked low-risk (36%); the month later tripled.
- **Categorization mistakes**: credit-card interest read as Entertainment, Zelle from a friend as Income, T-Mobile as Transport. The demo family has corrected two merchants; Gemini categorizes better than our small model.
- **Market prices are 2023 Amazon prices**; our title model ignores brands (Sony XM5 alone ≈ $117), so the hybrid leans on Gemini (weight 0.95).
- **Gemini free tier is small**: `gemini-3.5-flash` allows only 20 requests a day, so FinPilot uses `gemini-3.5-flash-lite` and keeps working without Gemini (our models + offline assistant).
- **Excel files** must be saved as CSV (extensions may not load remote libraries to read .xlsx).
- **One computer**: family profiles live in one browser; syncing a family across computers needs a server (next step).

## 7. What's next
Family sync across devices, real bank connections (open banking), parent approval of teen purchases, smarter allowance rules, a model trained on real (consented) family data.

## 8. Install and run
1. Download this repository (Code → Download ZIP) and unzip, or `git clone`.
2. Chrome → `chrome://extensions` → switch on **Developer mode** → **Load unpacked** → choose the `extension/` folder.
3. Click the FinPilot icon → the side panel opens → **Try the demo family** (PINs: Alex 1111, Sam 2222, Maya 3333, Leo 4444) or create your family.
4. Optional: More → Settings → paste a free Gemini API key (aistudio.google.com) and PayPal Sandbox keys.
5. Open any product page (e.g. Amazon) — the verdict card appears; or select a product and price → right-click → **Is this worth it?**

Retrain and re-export the models: `pip install -r requirements.txt`, then `python ml/data_prep.py`, the `ml/train_*.py` scripts, and `python ml/export_extension.py`. Results notebook: `notebooks/FinPilot_results.ipynb`. The earlier website version (v2) is kept in `backend/` and `web/`.

## 9. Sources
**Data**
- Misata, *US Bank and Card Transactions (preview)*, CC BY 4.0 — https://huggingface.co/datasets/misatadata/us-bank-transactions
- DoDataThings, *US Bank Transaction Categories v2*, MIT — https://huggingface.co/datasets/DoDataThings/us-bank-transaction-categories-v2
- *Amazon Products 2023* (milistu), MIT, derived from McAuley Lab Amazon Reviews 2023 — https://huggingface.co/datasets/milistu/AMAZON-Products-2023
- PayPal Sandbox (test accounts) — https://developer.paypal.com

**Models and libraries:** scikit-learn (logistic regression, ridge, gradient boosting), pandas, NumPy; the extension uses plain JavaScript (no external libraries).

**AI tools:** Google **Gemini** API (`gemini-3.5-flash-lite` in the extension; reads uploads, gives a price opinion, chats; used as a baseline). **Claude (Anthropic)** was used as a coding assistant to help write and test the code; the team made the product decisions recorded in `docs/spec.md`.

**Team:** _[names, schools]_

> This project is a prototype and is not financial advice.
