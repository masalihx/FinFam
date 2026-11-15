# FinPilot v3 tasks

## Phase 1: Engine in the browser

### Task 1: JS models match Python (S)
Models exported to JSON run in JS with the same outputs.
- [x] Categorizer, intent: same labels as Python on test vectors
- [x] Price: same prediction within $0.02; overspend, recurring: same probability within 1e-4
- Verify: `extension/test.html` shows no mismatches
- Files: `extension/lib/ml.js`, `extension/test.html`, `ml/export_extension.py`

### Task 2: Live features and money math match Python (M)
Overspend features for any day, recurring series, free cash, goal plans, usual price.
- [x] Overspend features for the demo family on a fixed date equal Python's (all 20 features)
- [x] Upcoming recurring payments list equals Python's for the same date
- [x] Free cash and goal plan equal Python's
- Verify: test page section "finance" all green
- Files: `extension/lib/features.js`, `extension/lib/finance.js`, `ml/export_extension.py`, `extension/test.html`

### Task 3: Store, demo family and profiles (S)
- [x] First run: create family (name, members, roles, PIN) or load the Carters
- [x] Demo transactions categorized by the JS model; seed corrections applied
- [x] Profile switch with PIN; parent/teen rights enforced in the store API
- Verify: test page section "store"; manual load in panel
- Files: `extension/lib/store.js`

### Checkpoint A
- [x] All test-page checks pass; demo family loads in < 3 s

## Phase 2: Product in the side panel

### Task 4: Side panel shell + Family overview (M)
- [x] Panel opens from the toolbar icon; profile picker → overview (KPIs, categories with risk, upcoming, who spent what, family goals)
- Verify: screenshot of the panel page; numbers equal the v2 website for the demo family
- Files: `extension/manifest.json`, `extension/panel.html`, `extension/panel.js`, `extension/panel.css`

### Task 5: Verdict everywhere (M)
- [x] `verdict.js` port; market price = our model blended with Gemini (cached)
- [x] Check tab in the panel; on-page card via background worker uses the same engine
- [x] Concert tickets $100 → Not worth it with a reasonable price; headphones $348 → Not worth it
- Verify: demo product page card + Check tab
- Files: `extension/lib/verdict.js`, `extension/background.js`, `extension/content.js`, `extension/panel.js`

### Task 6: Upcoming, Goals, My space (M)
- [x] Upcoming list (ML recurring + plans) and rest-of-month forecast; add/remove plan
- [x] Family + personal goals; add savings; teen space with allowance, earnings, cash expense
- Files: `extension/panel.js`, `extension/lib/store.js`

### Task 7: Needs & wants + Transactions with corrections (S)
- [x] Setup suggestions (ML) → parent confirms, limits saved and used by the verdict
- [x] Transactions list with filters; category fix updates same-merchant rows
- Files: `extension/panel.js`, `extension/lib/finance.js`

### Checkpoint B
- [ ] Every v2 website feature works in the panel for Alex and Maya

## Phase 3: Gemini

### Task 8: Uploads via Gemini (S)
- [x] Settings: Gemini key; receipt photo / PDF / CSV → preview → import (Excel: asks to save as CSV — no remote libraries allowed in MV3)
- Files: `extension/lib/gemini.js`, `extension/panel.js`, `extension/manifest.json`

### Task 9: Gemini assistant taught by context + our models as tools (M)
- [x] System instruction with family rules + examples from our datasets; tools = our JS ML functions
- [x] Offline fallback = intent model
- [ ] Python evaluation: tool choice accuracy (Gemini + context + tools) vs Gemini zero-shot vs intent model on the 47 test questions
- Files: `extension/lib/gemini.js`, `extension/lib/assistant.js`, `ml/eval_gemini_tools.py`

### Task 10: PayPal Sandbox from the extension (S, cut first if late)
- [x] Settings: PayPal sandbox keys; sync → transactions to the member with matching PayPal email (verify in real Chrome: CORS blocks it on a plain page)

### Checkpoint C
- [ ] Full demo script works from the extension only

## Phase 4: Ship
### Task 11: README, notebook, video script, push (S)
- [ ] README describes v3 (extension-only), new numbers, Gemini-with-context evaluation

---

# v4 (team feedback, 07:19 ET): simpler extension, no Gemini

Decisions: no Gemini at all (built-in ML only); side panel = exactly 2 parts (Advisor, Money in/out) with a
user-connected PayPal button; one 6-character family password (letters + digits), no member profiles;
FinAI card: verdict first, then the family's money state, then the average market price from our database.

### Task 12: Market price from the database (kNN) (M)
- [x] Similar products from Amazon Products 2023 by title (TF-IDF cosine); average/median price of neighbours
- [x] Python evaluation vs category median and ridge on the same unseen-store test set
- [x] Compact index exported to JSON; JS search matches Python on test titles

### Task 13: Family password store (S)
- [x] Create family → 6-char password (letters+digits), unique on this browser, stored as salted hash
- [x] Unlock with password; lock; demo family password DEMO26
- [x] No members/roles; all checks pass on test page

### Task 14: Built-in advisor without Gemini (M)
- [x] Remove Gemini code paths; intent model improved with more training phrases (test questions untouched)
- [x] Advisor answers from our tools only

### Task 15: Side panel = Advisor + Money (M)
- [x] Advisor: month status ("left to spend" per category), ML advice cards, "Is it worth it?" check, ask box
- [x] Money: quick add expense/income with live ML category, list with category fix, Connect PayPal dialog (user's own keys)

### Task 16: FinAI card (S)
- [x] Verdict first → family money state (e.g. "$X left for groceries this month") → market average from database
- [x] Short: at most 3 lines + buttons

### Task 17: Docs and push (S)

- [x] README, extension README, spec (v4 decisions), video script updated; pushed to GitHub

### Checkpoint v4
- [x] Engine tests 59/59 (test.html), panel checked in the built-in browser at side-panel width, card checked on card-test.html
- [ ] Team: load the unpacked extension in real Chrome, open an Amazon product page, connect PayPal with own Sandbox keys
