# FinPilot Chrome extension

On any product page FinPilot finds the product and price (or uses a product and price
you select), asks your family's FinPilot platform, and shows:
**Buy / Think about it / Not worth it**, the reasons, a **reasonable price for you**,
and what similar items cost.

## Install (developer mode)
1. Start the platform from the project root: `.venv/bin/uvicorn backend.main:app --port 8000`.
2. Open `chrome://extensions`, switch on **Developer mode** (top right).
3. Click **Load unpacked** and choose this `extension/` folder.
4. Click the FinPilot icon (puzzle piece → pin it) and log in, or pick a demo person (Alex, Sam, Maya, Leo).
5. Open a product page, for example http://localhost:8000/static/demo-product.html or any Amazon product.

## How it finds the product
1. schema.org `Product` data (most shops) → 2. `product:price:amount` / `og:` meta tags →
3. Amazon page layout → 4. microdata.
If nothing is found: **select the product name and price on the page → right-click →
“Is this worth it? (FinPilot)”**, or type them in the popup.

## Privacy
Only the product name, price and link go to the platform address in the popup
(default `http://localhost:8000`), with your login token. Shop pages never talk to the
platform directly; the background worker does.

This project is a prototype and is not financial advice.
