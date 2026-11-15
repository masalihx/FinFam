// "Connect PayPal" the real way: the user logs in on PayPal's own page (Log in with PayPal, Sandbox).
// The PayPal app (Client ID + Secret) is ours, the developers'; the user never sees or types keys.
// PayPal gives third-party apps the person's name and email, not their whole payment history, so FinPilot
// imports the person's payments that went through our Sandbox shop (the business account of our app).
const API = "https://api-m.sandbox.paypal.com";
const AUTHORIZE = "https://www.sandbox.paypal.com/connect";
const SCOPES = "openid profile email";

// ------------------------------------------------------------------ our app's keys (git-ignored file)

let appPromise = null;
export function paypalApp() {
  if (!globalThis.chrome?.runtime?.getURL) return Promise.resolve(null);
  appPromise ||= fetch(chrome.runtime.getURL("paypal.config.json"))
    .then((r) => (r.ok ? r.json() : null)).then((c) => (c?.client_id && c?.secret ? c : null)).catch(() => null);
  return appPromise;
}

const basic = (app) => `Basic ${btoa(`${app.client_id}:${app.secret}`)}`;

async function post(path, app, body) {
  const res = await fetch(`${API}${path}`, {
    method: "POST", headers: { Authorization: basic(app), "Content-Type": "application/x-www-form-urlencoded" }, body,
  }).catch(() => { throw new Error("Cannot reach PayPal. Check the internet connection."); });
  if (!res.ok) throw new Error(`PayPal refused the sign-in (${res.status}).`);
  return res.json();
}

// ------------------------------------------------------------------ pure helpers (tested in test.html)

export function authorizeUrl(clientId, redirectUri, state) {
  const q = new URLSearchParams({ flowEntry: "static", client_id: clientId, response_type: "code", scope: SCOPES, redirect_uri: redirectUri, state });
  return `${AUTHORIZE}?${q}`;
}

export function readRedirect(responseUrl, state) {
  const q = new URL(responseUrl).searchParams;
  if (q.get("error")) throw new Error(q.get("error") === "access_denied" ? "PayPal login was cancelled." : `PayPal: ${q.get("error_description") || q.get("error")}`);
  if (q.get("state") !== state) throw new Error("PayPal answer did not match this request. Try again.");
  if (!q.get("code")) throw new Error("PayPal did not return a login code.");
  return q.get("code");
}

export function profileOf(info) {
  const emails = info.emails || [];
  const email = (emails.find((e) => e.primary)?.value || emails[0]?.value || info.email || "").toLowerCase();
  return { name: info.name || [info.given_name, info.family_name].filter(Boolean).join(" ") || email, email, payer_id: info.payer_id || null };
}

function describe(t) {
  const info = t.transaction_info || {}, items = t.cart_info?.item_details || [];
  return `PAYPAL *${items[0]?.item_name || info.transaction_subject || info.transaction_note || "Payment"}`;
}

// The connected account IS our app's own PayPal account: PayPal lets us read its whole history, signs as they are.
export function ownPayments(details) {
  return details.map((t) => {
    const info = t.transaction_info || {};
    return { id: `pp-${info.transaction_id}`, date: (info.transaction_initiation_date || "").slice(0, 10),
      amount: Number(info.transaction_amount?.value || 0), description: describe(t), channel: "online" };
  }).filter((t) => t.date && t.amount);
}

// Our shop's history -> this person's payments. The shop received money = the family spent it (sign flips).
export function familyPayments(details, who) {
  return details.filter((t) => {
    const p = t.payer_info || {};
    return (who.email && (p.email_address || "").toLowerCase() === who.email) || (who.payer_id && p.account_id === who.payer_id);
  }).map((t) => {
    const info = t.transaction_info || {};
    return { id: `pp-${info.transaction_id}`, date: (info.transaction_initiation_date || "").slice(0, 10),
      amount: -Number(info.transaction_amount?.value || 0), description: describe(t), channel: "online" };
  }).filter((t) => t.date && t.amount);
}

// ------------------------------------------------------------------ connect, sync, disconnect

export const paypalConnected = (store) => !!store.data.settings.paypal_email;

export async function connectPaypal(store) {
  if (!globalThis.chrome?.identity?.launchWebAuthFlow) throw new Error("PayPal login works only inside the Chrome extension.");
  const app = await paypalApp();
  if (!app) throw new Error("PayPal isn't set up in this copy of FinPilot (paypal.config.json is missing, see README).");
  const state = crypto.randomUUID();
  const redirectUri = chrome.identity.getRedirectURL("paypal");
  let responseUrl;
  try {
    responseUrl = await chrome.identity.launchWebAuthFlow({ url: authorizeUrl(app.client_id, redirectUri, state), interactive: true });
  } catch (e) {
    throw new Error(/did not approve|cancel|closed/i.test(e.message) ? "PayPal login was cancelled." : `PayPal login failed: ${e.message}`);
  }
  const code = readRedirect(responseUrl, state);
  const tok = await post("/v1/oauth2/token", app, new URLSearchParams({ grant_type: "authorization_code", code }).toString());
  const res = await fetch(`${API}/v1/identity/oauth2/userinfo?schema=paypalv1.1`, { headers: { Authorization: `Bearer ${tok.access_token}` } });
  if (!res.ok) throw new Error(`PayPal did not share the profile (${res.status}).`);
  const who = profileOf(await res.json());
  if (!who.email && !who.payer_id) throw new Error("PayPal did not share the email. Turn on the Email attribute for Log in with PayPal.");
  await store.setSettings({ paypal_name: who.name, paypal_email: who.email, paypal_payer_id: who.payer_id,
    paypal_connected_at: new Date().toISOString().slice(0, 10), paypal_id: null, paypal_secret: null });
  return who;
}

export async function disconnectPaypal(store) {
  await store.setSettings({ paypal_name: null, paypal_email: null, paypal_payer_id: null, paypal_connected_at: null, paypal_synced_at: null });
}

const iso = (d) => d.toISOString().slice(0, 19) + "-0000";

export async function syncPaypal(store, days = 90) {
  const s = store.data.settings, app = await paypalApp();
  if (!paypalConnected(store)) throw new Error("Connect PayPal first.");
  if (!app) throw new Error("PayPal isn't set up in this copy of FinPilot.");
  const tok = (await post("/v1/oauth2/token", app, "grant_type=client_credentials")).access_token;
  const end = new Date(), details = [];
  for (let start = new Date(end - days * 86400000); start < end;) {
    const chunkEnd = new Date(Math.min(+end, +start + 31 * 86400000)); // at most 31 days per request
    for (let page = 1; ; page++) {
      const q = new URLSearchParams({ start_date: iso(start), end_date: iso(chunkEnd), fields: "all", page_size: "500", page: String(page) });
      const res = await fetch(`${API}/v1/reporting/transactions?${q}`, { headers: { Authorization: `Bearer ${tok}` } });
      if (res.status === 403) throw new Error("Transaction Search is off for our PayPal app.");
      if (!res.ok) throw new Error(`PayPal error ${res.status}.`);
      const data = await res.json();
      details.push(...(data.transaction_details || []));
      if (page >= Number(data.total_pages || 1)) break;
    }
    start = chunkEnd;
  }
  const shop = await fetch(`${API}/v1/identity/oauth2/userinfo?schema=paypalv1.1`, { headers: { Authorization: `Bearer ${tok}` } })
    .then((r) => (r.ok ? r.json() : {})).then(profileOf).catch(() => ({ email: "" }));
  const items = shop.email && shop.email === s.paypal_email ? ownPayments(details)
    : familyPayments(details, { email: s.paypal_email, payer_id: s.paypal_payer_id });
  const imported = await store.addTransactions(items, "paypal");
  await store.setSettings({ paypal_synced_at: new Date().toISOString().slice(0, 16).replace("T", " ") });
  return { found: items.length, imported };
}
