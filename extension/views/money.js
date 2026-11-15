// Part 2 of the panel: Money. The family writes expenses and income here (ML picks the category),
// fixes categories, and can connect its PayPal account (Log in with PayPal).
import { CATEGORY_NAMES, isSpending } from "../lib/finance.js";
import { monthIndex } from "../lib/dates.js";
import { connectPaypal, disconnectPaypal, paypalConnected, syncPaypal } from "../lib/paypal.js";
import { $, $$, busy, closeSheet, esc, formData, money as fmt, sheet, shortDate, toast } from "../lib/ui.js";

const PAGE = 40;
const LINK_ICON = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 13a5 5 0 0 0 7.07 0l3-3a5 5 0 0 0-7.07-7.07l-1.5 1.5"/><path d="M14 11a5 5 0 0 0-7.07 0l-3 3a5 5 0 0 0 7.07 7.07l1.5-1.5"/></svg>`;
const SOURCE = { model: "ML", user: "you", paypal: "PayPal" };
const catOptions = (sel) => Object.entries(CATEGORY_NAMES).map(([k, v]) => `<option value="${k}" ${k === sel ? "selected" : ""}>${esc(v)}</option>`).join("");

function txRow(t) {
  return `<li class="tx" data-id="${esc(t.id)}">
    <div class="tx-top"><span class="title">${esc(t.description)}</span><b class="num ${t.amount > 0 ? "pos" : ""}">${fmt(t.amount, 2)}</b></div>
    <div class="tx-bottom"><span class="xs muted">${shortDate(t.date)}${t.source === "paypal" ? " · PayPal" : ""} · category by ${SOURCE[t.category_source] || "file"}</span>
      <span class="tx-actions"><select class="select mini" data-cat aria-label="Category for ${esc(t.description)}">${catOptions(t.category)}</select>
        <button class="icon-btn" data-del aria-label="Delete ${esc(t.description)}" title="Delete">✕</button></span></div></li>`;
}

export async function money(el, app, state = { q: "", shown: PAGE }) {
  const s = app.store, tx = s.data.transactions, cur = monthIndex(app.today);
  const month = tx.filter((t) => monthIndex(t.date) === cur);
  const income = month.filter((t) => t.category === "income" && t.source !== "allowance").reduce((a, t) => a + t.amount, 0); // same rule as the Advisor
  const spent = -month.filter(isSpending).reduce((a, t) => a + t.amount, 0);
  const connected = paypalConnected(s);
  const q = state.q.toLowerCase();
  const list = [...tx].reverse().filter((t) => !q || t.description.toLowerCase().includes(q) || (CATEGORY_NAMES[t.category] || "").toLowerCase().includes(q));

  el.innerHTML = `<div class="stack">
    <section class="section" aria-labelledby="h-add">
      <div class="section-head"><h2 id="h-add">Add money in or out</h2>
        <button class="btn ${connected ? "ghost" : "paypal"} sm" id="paypal" aria-haspopup="dialog">${LINK_ICON}${connected ? `PayPal · ${esc((s.data.settings.paypal_name || "connected").split(" ")[0])}` : "Connect PayPal"}</button></div>
      <form id="add" class="stack" novalidate>
        <div class="seg block" role="group" aria-label="Expense or income">
          <button type="button" data-kind="expense" aria-pressed="true">Expense</button><button type="button" data-kind="income" aria-pressed="false">Income</button></div>
        <div class="grid2"><label class="field">Amount, $<input class="input" name="amount" type="number" min="0.01" step="0.01" inputmode="decimal" required placeholder="0.00"></label>
          <label class="field">Date<input class="input" name="date" type="date" value="${app.today}" max="${app.today}" required></label></div>
        <label class="field">What was it?<input class="input" name="description" required placeholder="Trader Joe's groceries" autocomplete="off"></label>
        <label class="field">Category<select class="select" name="category"><option value="">Auto (ML)</option>${catOptions("")}</select>
          <span class="xs muted" id="guess" aria-live="polite">Start typing — the ML model picks the category.</span></label>
        <button class="btn primary block" id="add-btn">Add expense</button>
      </form>
    </section>
    <div class="kpis"><div class="kpi"><div class="label">Spent this month</div><div class="value num">${fmt(spent)}</div></div>
      <div class="kpi"><div class="label">Income this month</div><div class="value num">${fmt(income)}</div></div></div>
    <section class="section" aria-labelledby="h-list">
      <div class="section-head"><h2 id="h-list">History</h2><span class="xs muted">${tx.length} entries</span></div>
      <input class="input" id="search" type="search" value="${esc(state.q)}" placeholder="Search description or category" aria-label="Search history">
      <ul class="tx-list" id="list">${list.slice(0, state.shown).map(txRow).join("") || `<li class="small muted" style="padding:12px 0">${tx.length ? "Nothing matches." : "No entries yet. Add the first one above."}</li>`}</ul>
      ${list.length > state.shown ? `<button class="btn ghost sm block" id="more">Show more (${list.length - state.shown} left)</button>` : ""}
    </section>
  </div>`;

  // add form: expense/income switch and live ML category
  const form = $("#add", el);
  let kind = "expense";
  $$("[data-kind]", form).forEach((b) => b.addEventListener("click", () => {
    kind = b.dataset.kind;
    $$("[data-kind]", form).forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    $("#add-btn", el).textContent = kind === "income" ? "Add income" : "Add expense";
    guess();
  }));
  const guess = () => {
    const d = form.description.value.trim();
    if (!d) { form.category.options[0].textContent = "Auto (ML)"; return; }
    const amount = (kind === "income" ? 1 : -1) * (Number(form.amount.value) || 1);
    const c = s.categorize([{ amount, description: d, channel: "manual" }])[0].category;
    form.category.options[0].textContent = `Auto (ML): ${CATEGORY_NAMES[c] || c}`;
    $("#guess", el).textContent = form.category.value ? "You picked the category yourself." : `ML thinks: ${CATEGORY_NAMES[c] || c}. Change it if it's wrong.`;
  };
  form.description.addEventListener("input", guess);
  form.amount.addEventListener("input", guess);
  form.category.addEventListener("change", guess);
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const f = formData(form);
    busy(e.submitter, async () => {
      await s.addEntry({ kind, amount: f.amount, description: f.description, date: f.date, category: f.category || null });
      const t = s.data.transactions.find((x) => x.description === f.description.trim() && x.date === f.date && x.id.startsWith("manual-"));
      toast(`Added ${kind === "income" ? "income" : "expense"} ${fmt(Number(f.amount), 2)} · ${CATEGORY_NAMES[t?.category] || ""}`);
      money(el, app, { q: "", shown: PAGE });
    });
  });

  // history: search, fix category, delete (press twice), show more
  let timer;
  $("#search", el).addEventListener("input", (e) => {
    clearTimeout(timer);
    timer = setTimeout(() => money(el, app, { q: e.target.value, shown: PAGE }).then(() => { const i = $("#search", el); i.focus(); i.setSelectionRange(i.value.length, i.value.length); }), 250);
  });
  $("#more", el)?.addEventListener("click", () => money(el, app, { ...state, shown: state.shown + PAGE }));
  $$(".tx", el).forEach((li) => {
    const id = li.dataset.id;
    $("[data-cat]", li).addEventListener("change", async (e) => {
      const n = await s.fixCategory(id, e.target.value);
      toast(n ? `Saved. ${n} other payment(s) from the same place were fixed too.` : "Saved. FinPilot will remember this.");
    });
    $("[data-del]", li).addEventListener("click", async (e) => {
      const b = e.currentTarget;
      if (!b.classList.contains("confirm")) { b.classList.add("confirm"); b.textContent = "Delete?"; return setTimeout(() => { b.classList.remove("confirm"); b.textContent = "✕"; }, 3000); }
      await s.deleteTransaction(id);
      li.remove();
      toast("Deleted.");
    });
  });

  $("#paypal", el).addEventListener("click", () => paypalSheet(app, () => money(el, app, state)));
}

function paypalSheet(app, done) {
  const s = app.store, st = s.data.settings;
  if (paypalConnected(s)) {
    const box = sheet(`<div class="section-head"><h2>PayPal</h2><button class="btn ghost sm" id="close">Close</button></div>
      <p class="small">Connected as <b>${esc(st.paypal_name || st.paypal_email)}</b>${st.paypal_email ? ` (${esc(st.paypal_email)})` : ""}${st.paypal_connected_at ? ` since ${esc(st.paypal_connected_at)}` : ""}.${st.paypal_synced_at ? ` Last import: ${esc(st.paypal_synced_at)}.` : ""}</p>
      <div class="stack"><button class="btn primary block" id="sync">Import payments (last 90 days)</button><button class="btn danger block" id="disconnect">Disconnect</button></div>
      <p class="xs muted">Disconnect forgets this PayPal account on this computer. Payments already imported stay.</p>`, "PayPal");
    $("#close", box).addEventListener("click", closeSheet);
    $("#sync", box).addEventListener("click", (e) => busy(e.currentTarget, async () => {
      const r = await syncPaypal(s);
      closeSheet(); done(); toast(r.found ? `PayPal: ${r.found} payments found, ${r.imported} new.` : "PayPal: no payments yet (new ones can take up to 3 hours to show).", 6000);
    }));
    $("#disconnect", box).addEventListener("click", async () => { await disconnectPaypal(s); closeSheet(); done(); toast("PayPal disconnected."); });
    return;
  }
  const box = sheet(`<div class="section-head"><h2>Connect PayPal</h2><button class="btn ghost sm" id="close">Cancel</button></div>
    <p class="small">Log in with your PayPal account on PayPal's own page. FinPilot never sees your password.</p>
    <ul class="steps small">
      <li>PayPal shares your <b>name and email</b> with FinPilot.</li>
      <li>FinPilot imports your payments made in shops that use FinPilot's PayPal (our Sandbox demo shop), and our ML sorts them into categories.</li></ul>
    <button class="btn paypal-login block" id="login">${LINK_ICON}Log in with PayPal</button>
    <p class="xs muted">Sandbox: test accounts and test money. Use a PayPal Sandbox personal account to log in.</p>`, "Connect PayPal");
  $("#close", box).addEventListener("click", closeSheet);
  $("#login", box).addEventListener("click", (e) => busy(e.currentTarget, async () => {
    const who = await connectPaypal(s);
    const r = await syncPaypal(s).catch((err) => ({ error: err.message }));
    closeSheet(); done();
    toast(r.error ? `Connected as ${who.name}, but the import failed: ${r.error}`
      : r.found ? `Connected as ${who.name}: ${r.found} payments found, ${r.imported} new.`
      : `Connected as ${who.name}. No payments through FinPilot's PayPal shop yet — PayPal shows new ones with up to a 3-hour delay. Use Import payments later.`, 9000);
  }));
}
