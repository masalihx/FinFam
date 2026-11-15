// Add data (Gemini uploads, PayPal) and Settings (keys, family).
import { CATEGORY_NAMES } from "../lib/finance.js";
import { DEFAULT_MODEL, extractTransactions } from "../lib/gemini.js";
import { syncPaypal } from "../lib/paypal.js";
import { $, $$, busy, esc, formData, toast } from "../lib/ui.js";

export async function add(el, app) {
  const s = app.store, me = s.me;
  el.innerHTML = `<div class="stack">
    <div><h1>Add data</h1><p class="xs muted" style="margin:0">Everything you add is yours in the family and also counts in the family's totals.</p></div>
    <section class="section stack" aria-labelledby="h-up"><h2 id="h-up">Receipt, statement or table <span class="tag brand">Gemini</span></h2>
      <p class="small muted" style="margin:0">Photo of a receipt, a PDF statement or a CSV table. Gemini reads it, our model sorts each line into a category, you check before importing.</p>
      <label class="btn ghost block" style="cursor:pointer">Choose a file<input type="file" id="file" accept="image/*,.pdf,.csv,.xlsx,.xls" class="sr-only"></label>
      <div id="result" aria-live="polite"></div></section>
    <section class="section stack" aria-labelledby="h-pp"><h2 id="h-pp">PayPal <span class="tag gray">Sandbox</span></h2>
      <p class="small muted" style="margin:0">Card and PayPal payments from the sandbox test account go to the family member whose PayPal email matches.</p>
      <label class="field">My PayPal sandbox email<input class="input" id="ppmail" type="email" value="${esc(s.member(me.id).paypal_email || "")}"></label>
      <div class="grid2"><button class="btn ghost" id="ppsave">Save email</button><button class="btn primary" id="ppsync">Sync PayPal</button></div></section>
  </div>`;
  $("#file", el).addEventListener("change", (e) => e.target.files[0] && upload(app, e.target.files[0], $("#result", el)));
  $("#ppsave", el).addEventListener("click", (e) => busy(e.currentTarget, async () => { await s.setPaypalEmail(me.id, $("#ppmail", el).value); toast("Saved."); }));
  $("#ppsync", el).addEventListener("click", (e) => busy(e.currentTarget, async () => {
    const r = await syncPaypal(app);
    toast(`Imported ${r.imported} new PayPal transaction(s)${r.found ? ` of ${r.found} found` : ""}.`);
  }));
}

async function upload(app, file, box) {
  box.innerHTML = `<div class="skeleton" style="height:60px" role="status" aria-label="Reading the file"></div><p class="xs muted">Gemini is reading “${esc(file.name)}”…</p>`;
  let r;
  try { r = await extractTransactions(app.store.data.settings, file, app.today); } catch (e) { box.innerHTML = `<p role="alert" class="small" style="color:var(--red)">${esc(e.message)}</p>`; return; }
  if (!r.rows.length) { box.innerHTML = `<p class="small">Gemini found no money movements in this file.</p>`; return; }
  const rows = app.store.categorize(r.rows.map((x, i) => ({ ...x, id: `up-${Date.now()}-${i}` })));
  const opts = (sel) => Object.entries(CATEGORY_NAMES).map(([k, v]) => `<option value="${k}" ${k === sel ? "selected" : ""}>${esc(v)}</option>`).join("");
  box.innerHTML = `<p class="small"><b>Found ${rows.length} line(s)</b> · ${esc(r.document_type)}. Check and fix before importing.</p>
    ${rows.map((x, i) => `<fieldset class="row" style="display:block;border:0;margin:0;padding:8px 0" data-row="${i}"><legend class="sr-only">Line ${i + 1}</legend>
      <div class="grid2"><input class="input" data-k="description" value="${esc(x.description)}" aria-label="Description"><input class="input" data-k="amount" type="number" step="0.01" value="${x.amount}" aria-label="Amount"></div>
      <div class="grid2" style="margin-top:6px"><input class="input" data-k="date" type="date" value="${esc(x.date)}" aria-label="Date"><select class="select" data-k="category" aria-label="Category">${opts(x.category)}</select></div>
      ${x.items.length ? `<p class="xs muted" style="margin:4px 0 0">${esc(x.items.join(", "))}</p>` : ""}</fieldset>`).join("")}
    <button class="btn primary block" id="import">Import</button>`;
  $("#import", box).addEventListener("click", (e) => busy(e.currentTarget, async () => {
    const items = $$("[data-row]", box).map((fs, i) => {
      const v = Object.fromEntries($$("[data-k]", fs).map((inp) => [inp.dataset.k, inp.value]));
      return { id: rows[i].id, date: v.date, description: v.description, amount: Number(v.amount), category: v.category, category_source: "user", channel: "upload" };
    });
    const n = await app.store.addTransactions(items, app.store.me.id, "upload");
    box.innerHTML = `<p class="small" style="color:var(--green)"><b>Imported ${n} transaction(s).</b> <a href="#transactions">See them</a></p>`;
  }));
}

export async function settings(el, app) {
  const s = app.store, set = s.data.settings, parent = s.me.role === "parent";
  el.innerHTML = `<div class="stack"><h1>Settings</h1>
    <form class="section stack" id="keys"><h2>Connections</h2>
      <p class="xs muted" style="margin:0">Keys stay in this browser only. Get a free Gemini key at aistudio.google.com → Get API key.</p>
      <label class="field">Gemini API key<input class="input" name="gemini_key" type="password" autocomplete="off" value="${esc(set.gemini_key || "")}"></label>
      <label class="field">Gemini model<input class="input" name="gemini_model" value="${esc(set.gemini_model || DEFAULT_MODEL)}"></label>
      <label class="field">PayPal Sandbox client ID<input class="input" name="paypal_id" autocomplete="off" value="${esc(set.paypal_id || "")}"></label>
      <label class="field">PayPal Sandbox secret<input class="input" name="paypal_secret" type="password" autocomplete="off" value="${esc(set.paypal_secret || "")}"></label>
      <button class="btn primary">Save</button></form>
    <section class="section"><h2>Family</h2>${s.members().map((m) => `<div class="row"><span>${esc(m.name)} <span class="tag ${m.role === "parent" ? "brand" : "gray"}">${m.role}</span></span><span class="xs muted">${esc(m.paypal_email || "")}</span></div>`).join("")}
      ${parent ? `<form id="member" class="grid2" style="margin-top:8px;grid-template-columns:1.3fr 1fr .8fr auto"><input class="input" name="name" required placeholder="Name" aria-label="Name"><select class="select" name="role" aria-label="Role"><option value="teen">Teen</option><option value="parent">Parent</option></select><input class="input" name="pin" required inputmode="numeric" pattern="\\d{4}" maxlength="4" placeholder="PIN" aria-label="PIN"><button class="btn ghost">Add</button></form>` : ""}</section>
    ${parent ? `<section class="section stack"><h2>Data</h2><p class="xs muted" style="margin:0">All data lives only in this browser.</p><button class="btn danger" id="wipe">Delete all FinPilot data</button></section>` : ""}
  </div>`;
  $("#keys", el).addEventListener("submit", (e) => { e.preventDefault(); busy(e.submitter, async () => { await s.setSettings(formData(e.target)); toast("Saved."); }); });
  $("#member", el)?.addEventListener("submit", (e) => { e.preventDefault(); busy(e.submitter, async () => { await s.addMember(formData(e.target)); await s.save(); app.refresh(); }); });
  $("#wipe", el)?.addEventListener("click", async () => {
    if (!confirm("Delete all FinPilot data in this browser? This cannot be undone.")) return;
    s.data = null; await s.save(); location.hash = ""; location.reload();
  });
}
