// Upcoming payments and goals.
import { monthSummary, monthlyFreeCash, planGoal, planGoals } from "../lib/finance.js";
import { $, $$, LIGHT, busy, closeSheet, dayLabel, esc, formData, money, pct, sheet } from "../lib/ui.js";
import { goalCard, upcomingItems } from "./home.js";

export async function upcoming(el, app) {
  const items = upcomingItems(app, 45);
  const sum = monthSummary(app.models, app.store.data.transactions, app.store.members(), app.today, app.store.limits());
  const byDay = {};
  for (const u of items) (byDay[u.date] ||= []).push(u);
  el.innerHTML = `<div class="stack">
    <div><h1>Upcoming</h1><p class="muted small" style="margin:0">Next 45 days · ${money(items.reduce((a, u) => a - u.amount, 0))} in total. Regular payments are found by our ML model.</p></div>
    <button class="btn primary" id="add">+ Add a plan</button>
    <section class="section" aria-label="Payments by day">${Object.entries(byDay).map(([d, list]) => `
      <h3 class="xs muted" style="text-transform:uppercase;letter-spacing:.05em;margin-top:8px">${dayLabel(d)}</h3>
      ${list.map((u) => `<div class="row"><div class="main"><div class="title">${esc(u.name)} ${u.kind === "plan" ? '<span class="tag brand">plan</span>' : ""}</div>
        <div class="xs muted">${u.kind === "plan" ? "planned by the family" : `${esc(u.frequency)} · ML ${pct(u.confidence)}`}${u.member ? ` · ${esc(u.member)}` : ""}</div></div>
        <span style="display:flex;gap:6px;align-items:center"><b class="num">${money(-u.amount)}</b>${u.kind === "plan" ? `<button class="btn ghost sm" data-del="${u.id}" aria-label="Remove ${esc(u.name)}">✕</button>` : ""}</span></div>`).join("")}`).join("") || `<p class="muted">Nothing found for the next 45 days.</p>`}</section>
    <section class="section" aria-labelledby="h-rest"><h2 id="h-rest">Rest of this month</h2><p class="xs muted">${sum.days_left} days left. What usually still goes out (ML forecast).</p>
      ${sum.categories.filter((c) => c.expected_rest_of_month).map((c) => `<div class="row"><span>${esc(c.name)} ${c.light ? `<span class="tag ${LIGHT[c.light][0]}">risk ${pct(c.overspend_probability)}</span>` : ""}</span><b class="num">~${money(c.expected_rest_of_month)}</b></div>`).join("")}</section>
  </div>`;
  $("#add", el).addEventListener("click", () => {
    const s = sheet(`<form class="stack" id="pf"><h2>Add a plan</h2><p class="small muted">A one-off expense: a birthday, a school trip, a repair.</p>
      <label class="field">What<input class="input" name="name" required></label>
      <div class="grid2"><label class="field">Amount, $<input class="input" name="amount" type="number" min="1" required></label><label class="field">Date<input class="input" name="date" type="date" required min="${app.today}"></label></div>
      <button class="btn primary block">Add</button></form>`, "Add a plan");
    $("#pf", s).addEventListener("submit", (e) => { e.preventDefault(); busy(e.submitter, async () => { await app.store.addPlan(formData(e.target)); closeSheet(); app.refresh(); }); });
  });
  $$("[data-del]", el).forEach((b) => b.addEventListener("click", async () => { await app.store.deletePlan(b.dataset.del); app.refresh(); }));
}

export function goalForm(app, personalOnly) {
  const parent = app.store.me.role === "parent";
  const s = sheet(`<form class="stack" id="gf"><h2>New goal</h2>
    <label class="field">Goal<input class="input" name="name" required placeholder="${personalOnly ? "Gaming PC" : "Kids' college fund"}"></label>
    <div class="grid2"><label class="field">Target, $<input class="input" name="target" type="number" min="1" required></label><label class="field">Saved, $<input class="input" name="saved" type="number" min="0" value="0"></label></div>
    <label class="field">Deadline<input class="input" name="deadline" type="date" required min="${app.today}"></label>
    ${parent && !personalOnly ? `<label class="field">Whose goal<select class="select" name="whose"><option value="family">Family goal</option><option value="me">My personal goal</option></select></label>` : ""}
    <button class="btn primary block">Save goal</button></form>`, "New goal");
  $("#gf", s).addEventListener("submit", (e) => {
    e.preventDefault();
    const f = formData(e.target);
    busy(e.submitter, async () => { await app.store.addGoal({ ...f, personal: personalOnly || !parent || f.whose === "me" }); closeSheet(); app.refresh(); });
  });
}

export function bindGoalButtons(el, app) {
  $$("[data-save]", el).forEach((b) => b.addEventListener("click", () => {
    const s = sheet(`<form class="stack" id="sf"><h2>Add savings</h2><label class="field">Amount, $<input class="input" name="amount" type="number" step="1" required></label><button class="btn primary block">Add</button></form>`, "Add savings");
    $("#sf", s).addEventListener("submit", (e) => { e.preventDefault(); busy(e.submitter, async () => { await app.store.addToGoal(b.dataset.save, formData(e.target).amount); closeSheet(); app.refresh(); }); });
  }));
  $$("[data-delgoal]", el).forEach((b) => b.addEventListener("click", () => busy(b, async () => {
    if (!confirm("Delete this goal?")) return;
    await app.store.deleteGoal(b.dataset.delgoal); app.refresh();
  })));
}

const goalActions = (g, can) => (can ? `<div style="display:flex;gap:6px;margin:-2px 0 8px"><button class="btn ghost sm" data-save="${g.id}">+ Add savings</button><button class="btn ghost sm" data-delgoal="${g.id}">Delete</button></div>` : "");

export async function goals(el, app) {
  const s = app.store, me = s.me, free = monthlyFreeCash(s.data.transactions, app.today);
  const names = Object.fromEntries(s.members().map((m) => [m.id, m.name]));
  const family = planGoals(s.data.goals.filter((g) => g.member_id === null), free, app.today);
  const personal = s.data.goals.filter((g) => g.member_id !== null).map((g) => planGoal(g, app.today));
  el.innerHTML = `<div class="stack">
    <div><h1>Goals</h1><p class="muted small" style="margin:0">The family keeps about ${money(free)} a month. FinPilot shares it between family goals, nearest deadline first.</p></div>
    <button class="btn primary" id="new">+ New goal</button>
    <section class="section"><h2>Family goals</h2>${family.map((g) => goalCard(g) + goalActions(g, me.role === "parent")).join("") || `<p class="muted small">No family goals yet.</p>`}</section>
    <section class="section"><h2>Personal goals</h2>${personal.map((g) => goalCard(g, names[g.member_id]) + goalActions(g, me.role === "parent" || g.member_id === me.id)).join("") || `<p class="muted small">No personal goals yet.</p>`}</section>
  </div>`;
  $("#new", el).addEventListener("click", () => goalForm(app, false));
  bindGoalButtons(el, app);
}

