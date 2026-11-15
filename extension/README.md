# FinPilot Chrome extension (v3: everything in the extension)

No server. Our ML models run in the browser; the family's data stays in `chrome.storage.local`.

## Install
1. `chrome://extensions` → **Developer mode** on → **Load unpacked** → choose this `extension/` folder.
2. Click the FinPilot icon: the **side panel** opens. Load the demo family (PINs: Alex 1111, Sam 2222, Maya 3333, Leo 4444) or create your own.
3. Optional: More → Settings → Gemini API key (free at aistudio.google.com) and PayPal Sandbox keys.

## Files
| Path | What |
|---|---|
| `panel.html`, `panel.js`, `panel.css`, `views/` | Side panel: first run, profiles, Home, Upcoming, Ask, Me, More (Goals, Check, Transactions, Add data, Postponed, Needs & wants, Settings) |
| `content.js`, `detect.js` | On shop pages: finds product and price (schema.org → meta tags → Amazon layout → microdata), shows the verdict card |
| `background.js` | Runs the engine for the card; opens the panel; right-click “Is this worth it?” |
| `lib/` | Engine: `ml.js`, `features.js`, `finance.js`, `verdict.js`, `assistant.js`, `gemini.js`, `paypal.js`, `store.js`, `dates.js`, `ui.js` |
| `models/` | Trained models exported from Python (`ml/export_extension.py`) |
| `data/` | Demo family, assistant tools/context, test fixtures |
| `test.html` | 41 checks that the JS engine matches Python (serve the folder over http and open it) |

## Privacy
Only when you use them: product title → Gemini (price opinion), uploaded files and chat messages → Gemini, PayPal Sandbox API.
Keys are stored only in this browser.

This project is a prototype and is not financial advice.
