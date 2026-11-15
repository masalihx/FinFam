// Transactions (with category fixes), needs & wants setup, postponed purchases, and the More menu.
import { CATEGORY_NAMES, setupSuggestions, upcomingRecurring } from "../lib/finance.js";
import { $, $$, busy, esc, money, shortDate, toast } from "../lib/ui.js";

export async function transactions(el, app, params) {
  const s = app.store, names = Object.fromEntries(s.members().map((m) => [m.id, m.name]));
  const f = { q: params.get("q") || "", member: params.get("member") || "", category: params.get("category") || "" };
  const list = [...s.data.transactions].reverse().filter((t) => (!f.q || t.description.toLowerCase().includes(f.q.toLowerCase()))
    && (!f.member || String(t.member_id) === f.member) && (!f.category || t.category === f.category)).slice(0, 150);
  const catOptions = (sel) => Object.entries(CATEGORY_NAMES).map(([k, v]) => `<option value="${k}" ${k === sel ? "selected" : ""}>${esc(v)}</option>`).join("");
  el.innerHTML = `<div class="stack">
    <div><h1>Transactions</h1><p class="xs muted" style="margin:0">The AI sets each category. Fix one and FinPilot fixes every payment from that merchant.</p></div>
    <form class="section stack" id="filters" role="search">
      <input class="input" name="q" value="${esc(f.q)}" placeholder="Search description" aria-label="Search description">
      <div class="grid2"><select class="select" name="member" aria-label="Who"><option value="">Everyone</option>${s.members().map((m) => `<option value="${m.id}" ${String(m.id) === f.member ? "selected" : ""}>${esc(m.name)}</option>`).join("")}</select>
        <select class="select" name="category" aria-label="Category"><option value="">All categories</option>${catOptions(f.category)}</select></div>
    </form>
    <section class="section">${list.map((t) => `<div class="row" style="display:block">
      <div style="display:flex;justify-content:space-between;gap:8px"><span class="title" style="min-width:0">${esc(t.description)}</span><b class="num" style="${t.amount > 0 ? "color:var(--green)" : ""}">${money(t.amount, 2)}</b></div>
      <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:4px">
        <span class="xs muted">${shortDate(t.date)} · ${esc(names[t.member_id] || "")} · ${t.category_source === "user" ? "you" : t.category_source === "file" ? "file" : "AI"}</span>
        <select class="select" style="width:auto;padding:2px 6px;font-size:12px" data-tx="${esc(t.id)}" aria-label="Category for ${esc(t.description)}">${catOptions(t.category)}</select></div></div>`).join("") || `<p class="muted">No transactions match.</p>`}</section>
  </div>`;
  const form = $("#filters", el);
  const go = () => { const p = new URLSearchParams([...new FormData(form)].filter(([, v]) => v)); location.hash = `transactions${p.toString() ? `?${p}` : ""}`; };
  form.addEventListener("change", go);
  form.addEventListener("submit", (e) => { e.preventDefault(); go(); });
  $$("[data-tx]", el).forEach((sel) => sel.addEventListener("change", async () => {
    const n = await s.fixCategory(sel.dataset.tx, sel.value);
    toast(`Saved. ${n} other payment(s) from this merchant updated.`);
    app.refresh();
  }));
}

export async function setup(el, app) {
  const s = app.store;
  if (s.me.role !== "parent") throw new Error("Only parents can change needs and wants.");
  const byCat = {};
  for (const u of upcomingRecurring(app.models, s.data.transactions, app.today, 400)) if (u.amount < 0) (byCat[u.category] ||= []).push(u.name);
  const rows = setupSuggestions(app.models, s.data.transactions, app.today, byCat).map((r) => {
    const saved = s.data.family.needs_wants[r.category];
    return saved ? { ...r, kind: saved.kind, suggested_limit: saved.limit ?? r.suggested_limit } : r;
  });
  el.innerHTML = `<div class="stack">
    <div><h1>Needs &amp; wants</h1><p class="small muted" style="margin:0">The AI looked at the last 6 months and found regular payments. Confirm what is a <b>need</b> and what is a <b>want</b>, and set monthly limits for wants. Verdicts use this.</p></div>
    <section class="section">${rows.map((r, i) => `<div class="row" style="display:block" data-i="${i}">
      <div style="display:flex;justify-content:space-between;gap:8px"><b>${esc(r.name)}</b><span class="num small">${money(r.usual_per_month)}/mo</span></div>
      <div class="xs muted">${esc(r.why)}</div>
      <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:6px">
        <span class="seg" role="group" aria-label="${esc(r.name)}: need or want"><button type="button" data-kind="need" aria-pressed="${r.kind === "need"}">Need</button><button type="button" data-kind="want" aria-pressed="${r.kind === "want"}">Want</button></span>
        <label class="small" style="display:flex;align-items:center;gap:6px">Limit $<input class="input" style="width:90px" type="number" min="0" step="10" value="${r.kind === "want" && r.suggested_limit != null ? Math.round(r.suggested_limit) : ""}" ${r.kind === "need" ? "disabled" : ""} aria-label="${esc(r.name)} monthly limit"></label>
      </div></div>`).join("")}</section>
    <button class="btn primary block" id="save">Save</button></div>`;
  $$("[data-i]", el).forEach((row) => $$("[data-kind]", row).forEach((b) => b.addEventListener("click", () => {
    $$("[data-kind]", row).forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    const input = $("input", row);
    input.disabled = b.dataset.kind === "need";
    if (input.disabled) input.value = "";
    else if (!input.value) input.value = Math.round(rows[row.dataset.i].usual_per_month);
  })));
  $("#save", el).addEventListener("click", (e) => busy(e.currentTarget, async () => {
    const items = $$("[data-i]", el).map((row) => {
      const kind = $('[aria-pressed="true"]', row).dataset.kind, v = $("input", row).value;
      return { category: rows[row.dataset.i].category, kind, monthly_limit: kind === "want" && v !== "" ? Number(v) : null };
    });
    await s.saveSetup(items);
    toast("Saved. Verdicts now use your needs, wants and limits.");
    location.hash = "home";
  }));
}

export async function postponed(el, app) {
  const s = app.store, names = Object.fromEntries(s.members().map((m) => [m.id, m.name]));
  const items = s.data.postponed;
  const waiting = items.filter((i) => i.status === "waiting").reduce((a, i) => a + i.price, 0);
  const kept = items.filter((i) => i.status === "dropped").reduce((a, i) => a + i.price, 0);
  el.innerHTML = `<div class="stack"><div><h1>Postponed</h1><p class="small muted" style="margin:0">${money(waiting)} waiting · ${money(kept)} kept by deciding not to buy</p></div>
    <section class="section">${items.map((i) => `<div class="row"><div class="main"><div class="title">${esc(i.title)}</div>
      <div class="xs muted">${esc(names[i.member_id] || "")} · reminder ${shortDate(i.remind_on)}</div></div>
      <div style="display:flex;gap:6px;align-items:center"><b class="num">${money(i.price, 2)}</b>${i.status === "waiting"
        ? `<button class="btn ghost sm" data-pp="${i.id}" data-st="bought">Bought</button><button class="btn ghost sm" data-pp="${i.id}" data-st="dropped">Not needed</button>`
        : `<span class="tag ${i.status === "dropped" ? "green" : "gray"}">${i.status === "dropped" ? "Kept the money" : "Bought"}</span>`}</div></div>`).join("")
      || `<p class="muted small">Nothing postponed. When FinPilot says “Not worth it”, press Postpone.</p>`}</section></div>`;
  $$("[data-pp]", el).forEach((b) => b.addEventListener("click", async () => { await s.setPostponedStatus(b.dataset.pp, b.dataset.st); app.refresh(); }));
}

export async function more(el, app) {
  const links = [["goals", "Goals", "Family and personal goals"], ["check", "Check a purchase", "Is it worth it?"],
    ["transactions", "Transactions", "Everyone's payments, fix categories"], ["add", "Add data", "Receipts, statements, PayPal"],
    ["postponed", "Postponed", "Things you decided to wait on"], ["setup", "Needs & wants", "Parents: limits for wants"],
    ["settings", "Settings", "Gemini key, PayPal, family"]];
  el.innerHTML = `<div class="stack"><h1>More</h1><nav class="section" aria-label="More">${links.map(([id, t, d]) =>
    `<a class="row" href="#${id}" style="text-decoration:none;color:inherit"><span class="main"><span class="title">${t}</span><span class="xs muted" style="display:block">${d}</span></span><span aria-hidden="true">›</span></a>`).join("")}</nav></div>`;
}
