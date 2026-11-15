// Home: how the family is doing this month.
import { CATEGORY_NAMES, monthSummary, planGoals, upcomingRecurring } from "../lib/finance.js";
import { addDays } from "../lib/dates.js";
import { BAR, LIGHT, avatar, dayLabel, esc, money, pct } from "../lib/ui.js";

export function upcomingItems(app, days = 30) {
  const s = app.store, names = Object.fromEntries(s.members().map((m) => [m.id, m.name]));
  const until = addDays(app.today, days);
  const regular = upcomingRecurring(app.models, s.data.transactions, app.today, days).filter((u) => u.amount < 0)
    .map((u) => ({ ...u, kind: "regular", member: names[u.member_id] }));
  const plans = s.data.plans.filter((p) => p.date >= app.today && p.date <= until)
    .map((p) => ({ date: p.date, name: p.name, amount: -Math.abs(p.amount), kind: "plan", id: p.id, member: names[p.member_id] }));
  return [...regular, ...plans].sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
}

export function goalCard(g, owner = "") {
  return `<div class="row" style="display:block">
    <div style="display:flex;justify-content:space-between;gap:8px"><b>${esc(g.name)}</b>${g.on_track === undefined ? "" : `<span class="tag ${g.on_track ? "green" : "red"}">${g.on_track ? "On track" : "Behind"}</span>`}</div>
    <div class="xs muted">${owner ? `${esc(owner)} · ` : ""}${money(g.saved)} of ${money(g.target)} by ${esc(g.deadline)}</div>
    <div class="bar" aria-hidden="true"><span style="width:${Math.min(100, g.progress * 100)}%;background:var(--brand)"></span></div>
    <div class="xs muted" style="margin-top:4px">Needs ${money(g.needed_per_month)}/month${g.allocated_per_month !== undefined ? ` · gets ${money(g.allocated_per_month)}` : ""}${g.projected_date ? ` · reached ${esc(g.projected_date)}` : ""}</div>
  </div>`;
}

function categoryRow(c) {
  const [tone, label] = LIGHT[c.light] || ["gray", "Not enough history"];
  const ratio = c.budget ? Math.min(1.25, Math.max(0, c.spent / c.budget)) : 0;
  return `<div class="row" style="display:block">
    <div style="display:flex;justify-content:space-between;gap:8px;align-items:center">
      <b>${esc(c.name)}</b><span class="tag ${tone}">${label}${c.overspend_probability != null ? ` · ${pct(c.overspend_probability)}` : ""}</span>
    </div>
    <div class="xs muted num">${money(c.spent)} of ${c.budget ? money(c.budget) : "—"}${c.limit_set_by_family ? " (your limit)" : " (usual)"}${c.expected_rest_of_month ? ` · usually ~${money(c.expected_rest_of_month)} more by month end` : ""}</div>
    <div class="bar" aria-hidden="true"><span style="width:${(ratio / 1.25) * 100}%;background:${BAR[c.light] || "var(--muted)"}"></span></div>
  </div>`;
}

export async function home(el, app) {
  const s = app.store, me = s.me;
  const sum = monthSummary(app.models, s.data.transactions, s.members(), app.today, s.limits());
  const up = upcomingItems(app);
  const due = up.reduce((a, u) => a - u.amount, 0);
  const goals = planGoals(s.data.goals.filter((g) => g.member_id === null), sum.free_cash_per_month, app.today);
  const cats = [...sum.categories].sort((a, b) => (b.overspend_probability ?? -1) - (a.overspend_probability ?? -1));
  const max = Math.max(1, ...sum.by_member.map((m) => m.spent));
  const setupBanner = s.data.family.setup_done ? "" : me.role === "parent"
    ? `<div class="section" style="background:var(--brand-soft);border-color:#b7e1d9"><b>Confirm needs and wants</b><p class="small" style="margin:4px 0 8px">The AI sorted your spending. One minute of checking decides when FinPilot says “Not worth it”.</p><a class="btn primary sm" href="#setup">Review</a></div>`
    : `<div class="section small muted">A parent hasn't confirmed the family's needs and wants yet; FinPilot uses the AI's suggestions.</div>`;

  el.innerHTML = `<div class="stack">
    <div><h1>Hi, ${esc(me.name)}</h1><p class="muted small" style="margin:0">${sum.days_left} days left this month</p></div>
    <a class="btn primary block" href="#check">Is it worth it? Check a purchase</a>
    ${setupBanner}
    <div class="kpis">
      <div class="kpi"><div class="label">Family spent this month</div><div class="value num">${money(sum.spent_this_month)}</div></div>
      <div class="kpi"><div class="label">Income this month</div><div class="value num">${money(sum.income_this_month)}</div></div>
      <div class="kpi"><div class="label">Kept per month</div><div class="value num">${money(sum.free_cash_per_month)}</div></div>
      <div class="kpi"><div class="label">Due in 30 days</div><div class="value num">${money(due)}</div></div>
    </div>
    <section class="section" aria-labelledby="h-risk"><div class="section-head"><h2 id="h-risk">This month by category</h2><span class="xs muted">ML risk of going over</span></div>${cats.map(categoryRow).join("")}</section>
    <section class="section" aria-labelledby="h-up"><div class="section-head"><h2 id="h-up">Coming up</h2><a class="small" href="#upcoming">All</a></div>
      ${up.slice(0, 5).map((u) => `<div class="row"><div class="main"><div class="title">${esc(u.name)}</div><div class="xs muted">${dayLabel(u.date)}${u.member ? ` · ${esc(u.member)}` : ""} · ${u.kind === "plan" ? "planned" : "regular"}</div></div><b class="num">${money(-u.amount)}</b></div>`).join("") || `<p class="muted small">Nothing due in the next 30 days.</p>`}</section>
    <section class="section" aria-labelledby="h-who"><div class="section-head"><h2 id="h-who">Who spent what</h2><span class="xs muted">teens count in the total</span></div>
      ${sum.by_member.map((m, i) => `<div class="row" style="display:block"><div style="display:flex;justify-content:space-between;align-items:center"><span style="display:flex;gap:8px;align-items:center">${avatar(m.name, i)}${esc(m.name)}</span><b class="num">${money(m.spent)}</b></div><div class="bar" aria-hidden="true"><span style="width:${(m.spent / max) * 100}%;background:var(--brand)"></span></div></div>`).join("")}</section>
    <section class="section" aria-labelledby="h-goals"><div class="section-head"><h2 id="h-goals">Family goals</h2><a class="small" href="#goals">Manage</a></div>
      ${goals.map((g) => goalCard(g)).join("") || `<p class="muted small">No family goals yet.</p>`}</section>
    ${Object.keys(sum.other_spending).length ? `<p class="xs muted">Bills this month: ${Object.entries(sum.other_spending).map(([c, v]) => `${esc(CATEGORY_NAMES[c] || c)} ${money(v)}`).join(" · ")}</p>` : ""}
  </div>`;
}
