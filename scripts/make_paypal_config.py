"""Write extension/paypal.config.json from .env so "Log in with PayPal" works in this copy of the extension.

Run from the project root:
    python3 scripts/make_paypal_config.py

The file is git-ignored: the PayPal Sandbox app's Client ID and Secret are ours (the developers'),
users only log in with their own PayPal account. Key values are never printed.
"""
import json
from pathlib import Path

env = {}
for line in Path(".env").read_text().splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")

client_id, secret = env.get("PAYPAL_CLIENT_ID", ""), env.get("PAYPAL_CLIENT_SECRET", "")
if not client_id or not secret:
    raise SystemExit("PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET must be set in .env")
out = Path("extension/paypal.config.json")
out.write_text(json.dumps({"mode": "sandbox", "client_id": client_id, "secret": secret}, indent=2) + "\n")
print(f"wrote {out} (client id {len(client_id)} chars, secret {len(secret)} chars)")
