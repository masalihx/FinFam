// PayPal Sandbox (test accounts, no real money): Transaction Search from inside the extension.
// Each transaction goes to the member whose PayPal email matches the payer; otherwise to whoever synced.
const API = "https://api-m.sandbox.paypal.com";

async function token(settings) {
  if (!settings.paypal_id || !settings.paypal_secret) throw new Error("Add PayPal Sandbox keys in More → Settings.");
  const res = await fetch(`${API}/v1/oauth2/token`, {
    method: "POST",
    headers: { Authorization: `Basic ${btoa(`${settings.paypal_id}:${settings.paypal_secret}`)}`, "Content-Type": "application/x-www-form-urlencoded" },
    body: "grant_type=client_credentials",
  }).catch(() => { throw new Error("Cannot reach PayPal."); });
  if (!res.ok) throw new Error(`PayPal sign-in failed (${res.status}). Check the keys.`);
  return (await res.json()).access_token;
}

const iso = (d) => d.toISOString().slice(0, 19) + "-0000";

function describe(t) {
  const info = t.transaction_info || {}, items = t.cart_info?.item_details || [];
  return `PAYPAL *${items[0]?.item_name || info.transaction_subject || info.transaction_note || t.payer_info?.payer_name?.alternate_full_name || "PayPal transaction"}`;
}

export async function syncPaypal(app, days = 90) {
  const s = app.store, tok = await token(s.data.settings);
  const byEmail = Object.fromEntries(s.members().filter((m) => m.paypal_email).map((m) => [m.paypal_email, m.id]));
  const end = new Date(), items = [];
  for (let start = new Date(end - days * 86400000); start < end;) {
    const chunkEnd = new Date(Math.min(+end, +start + 31 * 86400000));
    for (let page = 1; ; page++) {
      const q = new URLSearchParams({ start_date: iso(start), end_date: iso(chunkEnd), fields: "all", page_size: "500", page: String(page) });
      const res = await fetch(`${API}/v1/reporting/transactions?${q}`, { headers: { Authorization: `Bearer ${tok}` } });
      if (res.status === 403) throw new Error("PayPal refused Transaction Search. Enable it for the app in the developer dashboard.");
      if (!res.ok) throw new Error(`PayPal error ${res.status}.`);
      const data = await res.json();
      for (const t of data.transaction_details || []) {
        const info = t.transaction_info || {};
        const payer = (t.payer_info?.email_address || "").toLowerCase();
        items.push({ id: `pp-${info.transaction_id}`, date: (info.transaction_initiation_date || "").slice(0, 10),
          amount: Number(info.transaction_amount?.value || 0), description: describe(t), channel: "online",
          member_id: byEmail[payer] ?? s.me.id });
      }
      if (page >= Number(data.total_pages || 1)) break;
    }
    start = chunkEnd;
  }
  const imported = await s.addTransactions(items, s.me.id, "paypal");
  return { found: items.length, imported };
}
