# FinPilot Chrome extension

On any product page FinPilot finds the product name and price, asks your own FinPilot
platform whether this purchase puts your budget and goals at risk, and shows
🟢 Looks fine / 🟡 Think it over / 🔴 Better to postpone.

## Install (developer mode)
1. Start the platform: `.venv/bin/uvicorn backend.main:app --port 8000` and load data at http://localhost:8000.
2. Open `chrome://extensions`, switch on **Developer mode** (top right).
3. Click **Load unpacked** and choose this `extension/` folder.
4. Open a product page (or http://localhost:8000/static/demo-product.html).

## How it finds the price
schema.org `Product` data → `product:price:amount` / `og:` meta tags → Amazon page layout → microdata.
If nothing is found: open the popup and type the price, or select the price on the page,
right-click → **Check this price with FinPilot**.

## Privacy
Only the product name, price and link go to the platform address set in the popup
(default `http://localhost:8000`). Shop pages never talk to the platform directly;
the background worker does.

This project is a prototype and is not financial advice.
