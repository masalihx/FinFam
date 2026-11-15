// My space: a member's own money (allowance, earnings, spending, personal goals).
import { CATEGORY_NAMES, isSpending, planGoals } from "../lib/finance.js";
import { monthIndex, todayStr } from "../lib/dates.js";
import { $, busy, closeSheet, esc, formData, money, sheet, shortDate, toast } from "../lib/ui.js";
import { goalCard } from "./home.js";
import { bindGoalButtons, goalForm } from "./plan.js";

const sumOf = (list) => list.reduce((a, t) => a + t.amount, 0);

function moneyForm(app, title, sign) {
  const s = sheet(`<form class="stack" id="mf"><h2>${title}</h2>
    <label class="field">What<input class="input" name="description" required placeholder="${sign > 0 ? "Babysitting" : "Lunch with friends"}"></label>
    <div class="grid2"><label class="field">Amount, $<input class="input" name="amount" type="number" min="0.5" step="0.01" required></label>
      <label class="field">Date<input class="input" name="date" type="date" value="${todayStr()}"></label></div>
    <button class="btn primary block">Save</button></form>`, title);
  $("#mf", s).addEventListener("submit", (e) => {
    e.preventDefault();
    const f = formData(e.target);
    busy(e.submitter, async () => {
      const t = { id: `manual-${Date.now()}`, date: f.date, amount: sign * Math.abs(+f.amount), description: f.description, channel: "manual" };
      if (sign > 0) Object.assign(t, { category: "income", category_source: "user" });
      await app.store.addTransactions([t], app.store.me.id, "manual");
      closeSheet(); app.refresh();
    });
  });
}

export async function me(el, app, params) {
  const s = app.store, viewer = s.me;
  const memberId = Number(params.get("member")) || viewer.id;
  if (memberId !== viewer.id && viewer.role !== "parent") throw new Error("Only parents can open someone else's space.");
  const m = s.member(memberId), own = memberId === viewer.id, teen = m.role === "teen";
  const mine = s.data.transactions.filter((t) => t.member_id === memberId);
  const cur = monthIndex(app.today), month = mine.filter((t) => monthIndex(t.date) === cur);
  const allowance = sumOf(month.filter((t) => t.source === "allowance" && t.amount > 0));
  const earned = sumOf(month.filter((t) => t.category === "income" && t.source !== "allowance"));
  const spent = -sumOf(month.filter(isSpending));
  const last3 = mine.filter((t) => { const k = monthIndex(t.date); return k < cur && k >= cur - 3; });
  const saves = (sumOf(last3.filter((t) => t.category === "income")) + sumOf(last3.filter(isSpending))) / 3;
  const byCat = {};
  for (const t of month.filter(isSpending)) byCat[t.category] = (byCat[t.category] || 0) - t.amount;
  const goals = planGoals(s.data.goals.filter((g) => g.member_id === memberId), Math.max(0, saves), app.today);
  const teens = s.members().filter((x) => x.role === "teen");

  el.innerHTML = `<div class="stack">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">
      <div><h1>${own ? "My space" : `${esc(m.name)}'s space`}</h1><p class="xs muted" style="margin:0">Your own money and plans. It also counts in the family's totals.</p></div>
      ${viewer.role === "parent" && teens.length ? `<select class="select" id="who" style="width:auto" aria-label="Whose space"><option value="">Me</option>${teens.map((t) => `<option value="${t.id}" ${t.id === memberId ? "selected" : ""}>${esc(t.name)}</option>`).join("")}</select>` : ""}
    </div>
    <div class="kpis">
      ${teen ? `<div class="kpi"><div class="label">Allowance this month</div><div class="value num">${money(allowance)}</div><div class="xs muted">${m.allowance_amount ? `${money(m.allowance_amount)} per ${m.allowance_period}` : "not set"}</div></div>` : ""}
      <div class="kpi"><div class="label">Earned this month</div><div class="value num">${money(earned)}</div></div>
      <div class="kpi"><div class="label">Spent this month</div><div class="value num">${money(spent)}</div></div>
      ${teen ? `<div class="kpi"><div class="label">Left this month</div><div class="value num">${money(allowance + earned - spent)}</div></div>` : `<div class="kpi"><div class="label">Kept per month</div><div class="value num">${money(saves)}</div></div>`}
    </div>
    ${own ? `<div class="grid2"><button class="btn ghost" id="earn">+ I earned money</button><button class="btn ghost" id="cash">− I spent cash</button></div>` : ""}
    ${viewer.role === "parent" && teen ? `<section class="section stack" aria-labelledby="h-al"><h2 id="h-al">Allowance</h2>
      <form class="grid2" id="af"><label class="field">Amount, $<input class="input" name="amount" type="number" min="0" value="${m.allowance_amount ?? ""}"></label>
        <label class="field">Every<select class="select" name="period"><option value="week" ${m.allowance_period === "week" ? "selected" : ""}>week</option><option value="month" ${m.allowance_period === "month" ? "selected" : ""}>month</option></select></label>
        <button class="btn ghost">Save</button><button type="button" class="btn primary" id="pay">Pay now</button></form></section>` : ""}
    <section class="section"><div class="section-head"><h2>${own ? "My goals" : "Goals"}</h2>${own ? `<button class="btn ghost sm" id="goal">+ New</button>` : ""}</div>
      ${goals.map((g) => goalCard(g) + `<div style="display:flex;gap:6px;margin:-2px 0 8px"><button class="btn ghost sm" data-save="${g.id}">+ Add savings</button><button class="btn ghost sm" data-delgoal="${g.id}">Delete</button></div>`).join("") || `<p class="muted small">No personal goals yet.</p>`}</section>
    <section class="section"><h2>Where the money goes</h2>${Object.entries(byCat).sort((a, b) => b[1] - a[1]).map(([c, v]) => `<div class="row"><span>${esc(CATEGORY_NAMES[c] || c)}</span><b class="num">${money(v)}</b></div>`).join("") || `<p class="muted small">No spending this month.</p>`}</section>
    <section class="section"><h2>Recent</h2>${[...mine].reverse().slice(0, 12).map((t) => `<div class="row"><div class="main"><div class="title">${esc(t.description)}</div><div class="xs muted">${shortDate(t.date)} · ${esc(CATEGORY_NAMES[t.category] || t.category)}</div></div><b class="num" style="${t.amount > 0 ? "color:var(--green)" : ""}">${money(t.amount, 2)}</b></div>`).join("") || `<p class="muted small">Nothing yet.</p>`}</section>
  </div>`;
  $("#who", el)?.addEventListener("change", (e) => { location.hash = e.target.value ? `me?member=${e.target.value}` : "me"; });
  $("#earn", el)?.addEventListener("click", () => moneyForm(app, "I earned money", 1));
  $("#cash", el)?.addEventListener("click", () => moneyForm(app, "I spent cash", -1));
  $("#goal", el)?.addEventListener("click", () => goalForm(app, true));
  $("#af", el)?.addEventListener("submit", (e) => { e.preventDefault(); const f = formData(e.target); busy(e.submitter, async () => { await s.setAllowance(memberId, f.amount, f.period); toast("Allowance saved."); app.refresh(); }); });
  $("#pay", el)?.addEventListener("click", (e) => busy(e.currentTarget, async () => { await s.payAllowance(memberId); toast(`Paid ${money(m.allowance_amount)} to ${m.name}.`); app.refresh(); }));
  bindGoalButtons(el, app);
}
