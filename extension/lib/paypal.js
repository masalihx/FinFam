// PayPal Sandbox (test accounts, no real money). The family connects its own Sandbox app:
// the keys are checked with PayPal, kept only in this family's data on this computer, and used for Transaction Search.
const API = "https://api-m.sandbox.paypal.com";

async function token(id, secret) {
  if (!id || !secret) throw new Error("Enter both the Client ID and the Secret.");
  const res = await fetch(`${API}/v1/oauth2/token`, {
    method: "POST",
    headers: { Authorization: `Basic ${btoa(`${id}:${secret}`)}`, "Content-Type": "application/x-www-form-urlencoded" },
    body: "grant_type=client_credentials",
  }).catch(() => { throw new Error("Cannot reach PayPal. Check the internet connection."); });
  if (res.status === 401) throw new Error("PayPal did not accept these keys. Copy them again from your Sandbox app.");
  if (!res.ok) throw new Error(`PayPal sign-in failed (${res.status}).`);
  return (await res.json()).access_token;
}

const iso = (d) => d.toISOString().slice(0, 19) + "-0000";

function describe(t) {
  const info = t.transaction_info || {}, items = t.cart_info?.item_details || [];
  return `PAYPAL *${items[0]?.item_name || info.transaction_subject || info.transaction_note || t.payer_info?.payer_name?.alternate_full_name || "PayPal transaction"}`;
}

async function fetchTransactions(tok, days) {
  const end = new Date(), items = [];
  for (let start = new Date(end - days * 86400000); start < end;) {
    const chunkEnd = new Date(Math.min(+end, +start + 31 * 86400000)); // PayPal allows at most 31 days per request
    for (let page = 1; ; page++) {
      const q = new URLSearchParams({ start_date: iso(start), end_date: iso(chunkEnd), fields: "all", page_size: "500", page: String(page) });
      const res = await fetch(`${API}/v1/reporting/transactions?${q}`, { headers: { Authorization: `Bearer ${tok}` } });
      if (res.status === 403) throw new Error("PayPal refused Transaction Search. Turn it on for your app in the PayPal developer dashboard.");
      if (!res.ok) throw new Error(`PayPal error ${res.status}.`);
      const data = await res.json();
      for (const t of data.transaction_details || []) {
        const info = t.transaction_info || {};
        items.push({ id: `pp-${info.transaction_id}`, date: (info.transaction_initiation_date || "").slice(0, 10),
          amount: Number(info.transaction_amount?.value || 0), description: describe(t), channel: "online" });
      }
      if (page >= Number(data.total_pages || 1)) break;
    }
    start = chunkEnd;
  }
  return items.filter((t) => t.date && t.amount);
}

// Check the keys first; save them only if PayPal accepts them.
export async function connectPaypal(store, id, secret) {
  id = String(id || "").trim(); secret = String(secret || "").trim();
  await token(id, secret);
  await store.setSettings({ paypal_id: id, paypal_secret: secret, paypal_connected_at: new Date().toISOString().slice(0, 10) });
}

export async function disconnectPaypal(store) {
  await store.setSettings({ paypal_id: null, paypal_secret: null, paypal_connected_at: null, paypal_synced_at: null });
}

export const paypalConnected = (store) => !!(store.data.settings.paypal_id && store.data.settings.paypal_secret);

export async function syncPaypal(store, days = 90) {
  const s = store.data.settings;
  if (!paypalConnected(store)) throw new Error("Connect PayPal first.");
  const items = await fetchTransactions(await token(s.paypal_id, s.paypal_secret), days);
  const imported = await store.addTransactions(items, "paypal");
  await store.setSettings({ paypal_synced_at: new Date().toISOString().slice(0, 16).replace("T", " ") });
  return { found: items.length, imported };
}
