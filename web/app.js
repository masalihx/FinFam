// FinPilot website. Talks to the FastAPI backend on the same origin (session cookie).
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = (x, d = 0) => (x < 0 ? "−$" : "$") + Math.abs(Number(x) || 0).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
const pct = (p) => (p == null ? "—" : Math.round(p * 100) + "%");
const fmtDate = (s) => new Date(s + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" });
const weekday = (s) => new Date(s + "T00:00:00").toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
const COLORS = ["#0f766e", "#f59e0b", "#6366f1", "#ec4899", "#0ea5e9", "#22c55e", "#a855f7", "#64748b", "#14b8a6", "#ef4444"];
const AVATAR = ["#0f766e", "#6366f1", "#ec4899", "#f59e0b", "#0ea5e9"];

const state = { me: null, room: null, categories: {}, charts: [] };

// ------------------------------------------------------------------ API

async function api(path, opts = {}) {
  const init = { credentials: "same-origin", ...opts };
  if (opts.body && !(opts.body instanceof FormData)) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(opts.body);
  }
  const res = await fetch(path, init);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = typeof data.detail === "string" ? data.detail : Array.isArray(data.detail) ? data.detail.map((d) => d.msg).join("; ") : `Request failed (${res.status})`;
    const err = new Error(msg);
    err.status = res.status;
    throw err;
  }
  return data;
}

function toast(text, ms = 3500) {
  const t = $("#toast");
  t.textContent = text;
  t.classList.remove("hidden");
  clearTimeout(toast.t);
  toast.t = setTimeout(() => t.classList.add("hidden"), ms);
}

async function withBusy(btn, fn) {
  const html = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner ${btn.classList.contains("btn-primary") ? "" : "spinner-dark"}"></span>`;
  try { return await fn(); } catch (e) { toast(e.message); } finally { btn.disabled = false; btn.innerHTML = html; }
}

function avatar(name, i = 0, cls = "") {
  return `<div class="avatar ${cls}" style="background:${AVATAR[i % AVATAR.length]}">${esc((name || "?")[0].toUpperCase())}</div>`;
}

function destroyCharts() { state.charts.forEach((c) => c.destroy()); state.charts = []; }

function modal(html) {
  $("#modal-card").innerHTML = html;
  $("#modal").classList.remove("hidden");
}
function closeModal() { $("#modal").classList.add("hidden"); }
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });

const LIGHT = {
  red: { pill: "pill-red", label: "High risk", color: "var(--red)" },
  yellow: { pill: "pill-yellow", label: "Watch", color: "var(--yellow)" },
  green: { pill: "pill-green", label: "On track", color: "var(--green)" },
};
const DECISION = {
  buy: { icon: "🟢", cls: "pill-green" },
  think: { icon: "🟡", cls: "pill-yellow" },
  not_worth_it: { icon: "🔴", cls: "pill-red" },
};

// ------------------------------------------------------------------ auth screens

const DEMO = [
  { key: "alex", name: "Alex", role: "Parent" },
  { key: "sam", name: "Sam", role: "Parent" },
  { key: "maya", name: "Maya", role: "Teen, 17" },
  { key: "leo", name: "Leo", role: "Teen, 14" },
];

function showAuth(mode = "login") {
  $("#app").classList.add("hidden");
  $("#chat-toggle").classList.add("hidden");
  $("#chat").classList.add("hidden");
  $("#auth").classList.remove("hidden");
  $("#demo-people").innerHTML = DEMO.map((p, i) => `
    <button class="demo-person" data-demo="${p.key}">
      <div class="flex justify-center">${avatar(p.name, i)}</div>
      <div class="font-semibold text-sm mt-2">${p.name}</div><div class="text-xs text-slate-500">${p.role}</div>
    </button>`).join("");
  $$("[data-demo]").forEach((b) => b.addEventListener("click", () => withBusy(b, async () => {
    await api(`/api/demo/login?who=${b.dataset.demo}`, { method: "POST" });
    await boot();
  })));
  renderAuthCard(mode);
}

function renderAuthCard(mode) {
  const card = $("#auth-card");
  if (mode === "room") {
    card.innerHTML = `
      <h2 class="h1">Set up your family room</h2>
      <p class="sub mt-1">A room is your family's shared space. Parents create it; everyone else joins with the invite code.</p>
      <div class="tabs mt-6"><button class="tab active" data-rt="create">Create a room</button><button class="tab" data-rt="join">Join with a code</button></div>
      <form id="room-form" class="mt-5 space-y-4"></form>`;
    const draw = (t) => {
      $$("[data-rt]").forEach((x) => x.classList.toggle("active", x.dataset.rt === t));
      $("#room-form").innerHTML = t === "create"
        ? `<label class="field">Family name<input class="input" name="name" placeholder="The Smith family" required></label>
           <button class="btn btn-primary w-full">Create room</button>`
        : `<label class="field">Invite code<input class="input uppercase" name="code" placeholder="SMITH-4821" required></label>
           <label class="field">I am a<select class="select" name="role"><option value="teen">Teen</option><option value="parent">Parent</option></select></label>
           <button class="btn btn-primary w-full">Join room</button>`;
      $("#room-form").dataset.type = t;
    };
    draw("create");
    $$("[data-rt]").forEach((x) => x.addEventListener("click", () => draw(x.dataset.rt)));
    $("#room-form").addEventListener("submit", (e) => {
      e.preventDefault();
      const f = Object.fromEntries(new FormData(e.target));
      withBusy(e.target.querySelector("button"), async () => {
        if (e.target.dataset.type === "create") await api("/api/rooms", { method: "POST", body: { name: f.name } });
        else await api("/api/rooms/join", { method: "POST", body: { code: f.code, role: f.role } });
        await boot();
      });
    });
    return;
  }
  const signup = mode === "signup";
  card.innerHTML = `
    <h2 class="h1">${signup ? "Create your account" : "Welcome back"}</h2>
    <p class="sub mt-1">${signup ? "Parents and teens each get their own login." : "Log in to your family room."}</p>
    <div class="tabs mt-6"><button class="tab ${signup ? "" : "active"}" data-mode="login">Log in</button><button class="tab ${signup ? "active" : ""}" data-mode="signup">Sign up</button></div>
    <form id="auth-form" class="mt-5 space-y-4">
      ${signup ? `<label class="field">Your name<input class="input" name="name" placeholder="Alex" required></label>` : ""}
      <label class="field">Email<input class="input" name="email" type="email" autocomplete="email" required></label>
      <label class="field">Password<input class="input" name="password" type="password" minlength="8" autocomplete="${signup ? "new-password" : "current-password"}" required></label>
      <button class="btn btn-primary w-full">${signup ? "Create account" : "Log in"}</button>
    </form>`;
  $$("[data-mode]").forEach((b) => b.addEventListener("click", () => renderAuthCard(b.dataset.mode)));
  $("#auth-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target));
    withBusy(e.target.querySelector("button"), async () => {
      await api(signup ? "/api/auth/register" : "/api/auth/login", { method: "POST", body: f });
      await boot();
    });
  });
}

// ------------------------------------------------------------------ shell

const NAV = [
  { sep: "Family" },
  { id: "family", label: "Overview", ico: "▦" },
  { id: "upcoming", label: "Upcoming", ico: "⏱" },
  { id: "goals", label: "Goals", ico: "⚑" },
  { id: "transactions", label: "Transactions", ico: "≡" },
  { sep: "Me" },
  { id: "me", label: "My space", ico: "☺" },
  { id: "check", label: "Check a purchase", ico: "✓" },
  { id: "postponed", label: "Postponed", ico: "⏸" },
  { id: "add", label: "Add data", ico: "＋" },
  { sep: "Room" },
  { id: "settings", label: "Settings", ico: "⚙" },
];

function renderShell() {
  const m = state.me.member;
  $("#auth").classList.add("hidden");
  $("#app").classList.remove("hidden");
  $("#chat-toggle").classList.remove("hidden");
  $("#room-name").textContent = m.room_name;
  $("#room-code").textContent = `Invite code · ${m.room_code}`;
  $("#me-name").textContent = state.me.user.name;
  $("#me-role").textContent = m.role === "parent" ? "Parent" : "Teen";
  const idx = Math.max(0, (state.room?.members || []).findIndex((x) => x.id === m.id));
  $("#me-avatar").outerHTML = `<div class="avatar" id="me-avatar" style="background:${AVATAR[idx % AVATAR.length]}">${esc(state.me.user.name[0])}</div>`;
  $("#me-avatar-sm").outerHTML = `<div class="avatar avatar-sm" id="me-avatar-sm" style="background:${AVATAR[idx % AVATAR.length]}">${esc(state.me.user.name[0])}</div>`;
  $("#nav").innerHTML = NAV.map((n) => n.sep ? `<div class="nav-sep">${n.sep}</div>`
    : `<a href="#/${n.id}" class="nav-item" data-nav="${n.id}"><span class="ico">${n.ico}</span>${n.label}</a>`).join("");
}

$("#room-code").addEventListener("click", () => {
  navigator.clipboard?.writeText(state.me.member.room_code);
  toast(`Invite code ${state.me.member.room_code} copied. Family members join with it.`);
});
$("#logout").addEventListener("click", async () => { await api("/api/auth/logout", { method: "POST" }); state.me = null; showAuth(); });
$("#menu-open").addEventListener("click", () => $("#sidebar").classList.add("open"));
$("#menu-close").addEventListener("click", () => $("#sidebar").classList.remove("open"));

// ------------------------------------------------------------------ router

const ROUTES = {};
async function route() {
  if (!state.me?.member) return;
  const id = (location.hash.replace(/^#\//, "") || "family").split("?")[0];
  const view = ROUTES[id] ? id : "family";
  $$("[data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === view));
  $("#sidebar").classList.remove("open");
  destroyCharts();
  $("#view").innerHTML = `<div class="skeleton h-9 w-64"></div><div class="grid md:grid-cols-4 gap-4 mt-6">${'<div class="skeleton h-24"></div>'.repeat(4)}</div><div class="skeleton h-72 mt-6"></div>`;
  try {
    await ROUTES[view]($("#view"));
  } catch (e) {
    if (e.status === 401) return showAuth();
    if (e.status === 409) return renderEmpty($("#view"), e.message);
    $("#view").innerHTML = `<div class="card text-red-700">${esc(e.message)}</div>`;
  }
  window.scrollTo(0, 0);
}
window.addEventListener("hashchange", route);

function renderEmpty(el, message) {
  el.innerHTML = `
    <div class="card text-center py-12">
      <div class="text-4xl">📥</div>
      <h2 class="h2 mt-3">Let's bring in your family's money</h2>
      <p class="sub mt-1 max-w-md mx-auto">${esc(message)}</p>
      <a href="#/add" class="btn btn-primary mt-5">Add data</a>
    </div>`;
}

function header(title, sub, actions = "") {
  return `<div class="flex items-end justify-between flex-wrap gap-3 mb-6">
    <div><h1 class="h1">${title}</h1>${sub ? `<p class="sub mt-1">${sub}</p>` : ""}</div><div class="flex gap-2">${actions}</div></div>`;
}

// ------------------------------------------------------------------ Family overview

ROUTES.family = async (el) => {
  const o = await api("/api/overview");
  const m = state.me.member;
  const setupBanner = !m.setup_done ? (m.role === "parent"
    ? `<div class="card card-tight mb-6 flex items-center justify-between gap-3 flex-wrap" style="background:#f0fdfa;border-color:#99f6e4">
         <div><div class="font-semibold">Tell FinPilot what your family needs and what is a want</div>
         <div class="sub">The AI already sorted your spending. Check it in one minute: it decides when to say “Not worth it”.</div></div>
         <button class="btn btn-primary" id="open-setup">Review needs &amp; wants</button></div>`
    : `<div class="card card-tight mb-6 sub">A parent hasn't confirmed the family's needs and wants yet. FinPilot uses the AI's suggestions until then.</div>`) : "";
  const cats = [...o.categories].sort((a, b) => (b.overspend_probability ?? -1) - (a.overspend_probability ?? -1));
  const upcomingTotal = o.upcoming.reduce((s, u) => s + -u.amount, 0);
  el.innerHTML = `
    ${header(`Hi, ${esc(state.me.user.name.split(" ")[0])}`, `${esc(m.room_name)} · ${o.days_left} days left in ${new Date(o.today).toLocaleDateString("en-US", { month: "long" })}`,
      `<a href="#/check" class="btn btn-primary">Check a purchase</a>`)}
    ${setupBanner}
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
      ${kpi("Family spent this month", money(o.spent_this_month), "everyone, incl. teens")}
      ${kpi("Income this month", money(o.income_this_month))}
      ${kpi("Kept per month", money(o.free_cash_per_month), "6-month average after spending")}
      ${kpi("Due in next 30 days", money(upcomingTotal), `${o.upcoming.length} payments`)}
    </div>
    <div class="grid lg:grid-cols-3 gap-4 mt-4">
      <section class="card lg:col-span-2">
        <div class="flex items-center justify-between gap-2"><h2 class="h2">This month by category</h2><span class="text-xs text-slate-500">Risk = ML chance of ending above your usual level or limit</span></div>
        <div class="mt-4 space-y-4">${cats.map(catRow).join("")}</div>
        ${Object.keys(o.other_spending).length ? `<div class="mt-5 pt-4 border-t border-slate-100 text-sm text-slate-600">Bills &amp; essentials this month: ${Object.entries(o.other_spending).sort((a, b) => b[1] - a[1]).map(([c, v]) => `${esc(state.categories[c] || c)} <b>${money(v)}</b>`).join(" · ")}</div>` : ""}
      </section>
      <section class="card">
        <div class="flex items-center justify-between"><h2 class="h2">Coming up</h2><a href="#/upcoming" class="link text-sm">All</a></div>
        <div class="mt-2">${o.upcoming.slice(0, 7).map(upRow).join("") || '<p class="sub mt-2">Nothing due in the next 30 days.</p>'}</div>
      </section>
    </div>
    <div class="grid lg:grid-cols-3 gap-4 mt-4">
      <section class="card">
        <h2 class="h2">Who spent what</h2><p class="sub">This month. Teens' spending counts in the family total.</p>
        <div class="mt-4 space-y-3">${memberBars(o.by_member)}</div>
      </section>
      <section class="card lg:col-span-2">
        <div class="flex items-center justify-between"><h2 class="h2">Family goals</h2><a href="#/goals" class="link text-sm">Manage</a></div>
        <div class="grid md:grid-cols-2 gap-3 mt-3">${o.goals.map((g) => goalCard(g, false)).join("") || '<p class="sub">No family goals yet.</p>'}</div>
      </section>
    </div>
    <section class="card mt-4"><h2 class="h2">Last 6 months</h2><div class="h-72 mt-3"><canvas id="trend"></canvas></div></section>`;
  $("#open-setup")?.addEventListener("click", openSetup);
  bindBudgetButtons(el);
  trendChart($("#trend"), o.trend);
};

function kpi(label, value, hint = "") {
  return `<div class="card card-tight"><div class="label">${label}</div><div class="kpi-value">${value}</div>${hint ? `<div class="text-xs text-slate-400 mt-0.5">${hint}</div>` : ""}</div>`;
}

function catRow(c) {
  const l = LIGHT[c.light];
  const ratio = c.budget ? Math.max(0, Math.min(1.25, c.spent / c.budget)) : 0;
  const pill = l ? `<span class="pill ${l.pill}">${l.label} · ${pct(c.overspend_probability)}</span>` : '<span class="pill pill-gray">Not enough history</span>';
  return `<div>
    <div class="flex items-center justify-between gap-3 text-sm">
      <div class="font-semibold">${esc(c.name)}</div>
      <div class="flex items-center gap-2 text-slate-600">
        <span>${money(c.spent)} of <button class="underline decoration-dotted underline-offset-2" data-budget="${c.category}" title="${c.limit_set_by_family ? "Limit set by your family" : "Usual level learned from your data"}">${c.budget ? money(c.budget) : "—"}</button>${c.limit_set_by_family ? ' <span class="pill pill-teal">limit</span>' : ""}</span>${pill}
      </div>
    </div>
    <div class="bar mt-2"><div style="width:${(ratio / 1.25) * 100}%;background:${l ? l.color : "#94a3b8"}"></div></div>
    ${c.expected_rest_of_month ? `<div class="text-xs text-slate-400 mt-1">Usually another ~${money(c.expected_rest_of_month)} by month end</div>` : ""}
  </div>`;
}

function bindBudgetButtons(el) {
  $$("[data-budget]", el).forEach((b) => b.addEventListener("click", () => {
    if (state.me.member.role !== "parent") return toast("Only parents can set limits.");
    openSetup();
  }));
}

function upRow(u) {
  return `<div class="row-line">
    <div class="min-w-0"><div class="font-medium truncate">${esc(u.name)}</div>
      <div class="text-xs text-slate-500">${weekday(u.date)}${u.member ? ` · ${esc(u.member)}` : ""} · ${u.kind === "plan" ? "planned" : "regular"}</div></div>
    <div class="font-semibold whitespace-nowrap">${money(-u.amount)}</div></div>`;
}

function memberBars(rows) {
  const max = Math.max(1, ...rows.map((r) => r.spent));
  return rows.map((r, i) => `<div>
    <div class="flex items-center justify-between text-sm"><div class="flex items-center gap-2">${avatar(r.name, i, "avatar-sm")}<span class="font-medium">${esc(r.name)}</span><span class="text-xs text-slate-400">${r.role}</span></div><b>${money(r.spent)}</b></div>
    <div class="bar mt-1.5"><div style="width:${(r.spent / max) * 100}%;background:${AVATAR[i % AVATAR.length]}"></div></div></div>`).join("");
}

function goalCard(g, editable, owner = "") {
  return `<div class="border border-slate-200 rounded-2xl p-4">
    <div class="flex items-start justify-between gap-2">
      <div><div class="font-semibold">${esc(g.name)}</div><div class="text-xs text-slate-500">${owner ? esc(owner) + " · " : ""}${money(g.saved)} of ${money(g.target)} · by ${fmtDate(g.deadline)} ${new Date(g.deadline).getFullYear()}</div></div>
      ${g.on_track === undefined ? "" : `<span class="pill ${g.on_track ? "pill-green" : "pill-red"}">${g.on_track ? "On track" : "Behind"}</span>`}
    </div>
    <div class="bar mt-3"><div style="width:${Math.min(100, g.progress * 100)}%;background:var(--brand)"></div></div>
    <div class="grid grid-cols-3 gap-2 mt-3 text-sm">
      <div><div class="label">Needs / month</div><b>${money(g.needed_per_month)}</b></div>
      ${g.allocated_per_month !== undefined ? `<div><div class="label">Gets now</div><b>${money(g.allocated_per_month)}</b></div>` : `<div><div class="label">Months left</div><b>${g.months_left}</b></div>`}
      ${g.projected_date ? `<div><div class="label">Reached</div><b>${esc(g.projected_date.length === 10 ? fmtDate(g.projected_date) + " " + g.projected_date.slice(0, 4) : g.projected_date)}</b></div>` : ""}
    </div>
    ${editable ? `<div class="flex gap-2 mt-3"><button class="btn btn-ghost btn-sm" data-goal-save="${g.id}">+ Add savings</button><button class="btn btn-ghost btn-sm" data-goal-del="${g.id}">Delete</button></div>` : ""}
  </div>`;
}

function trendChart(canvas, trend) {
  if (!canvas || !trend.length) return;
  const cats = ["housing", "groceries", "dining", "shopping", "transportation", "utilities", "insurance", "subscriptions", "entertainment", "health"];
  const datasets = cats.map((c, i) => ({ label: state.categories[c] || c, data: trend.map((r) => Math.max(0, r[c] || 0)), backgroundColor: COLORS[i], borderRadius: 4 }))
    .filter((d) => d.data.some((v) => v > 0));
  state.charts.push(new Chart(canvas, {
    type: "bar",
    data: { labels: trend.map((r) => new Date(r.month + "-01T00:00:00").toLocaleDateString("en-US", { month: "short" })), datasets },
    options: { maintainAspectRatio: false, plugins: { legend: { position: "bottom", labels: { boxWidth: 10, font: { size: 11 } } } },
      scales: { x: { stacked: true, grid: { display: false } }, y: { stacked: true, ticks: { callback: (v) => "$" + v / 1000 + "k" } } } },
  }));
}

// ------------------------------------------------------------------ Setup wizard (needs and wants)

async function openSetup() {
  modal(`<div class="p-6"><div class="skeleton h-8 w-72"></div><div class="skeleton h-64 mt-4"></div></div>`);
  let data;
  try { data = await api("/api/setup/suggestions"); } catch (e) { closeModal(); return toast(e.message); }
  const rows = data.suggestions;
  modal(`
    <div class="p-6">
      <h2 class="h1">Needs &amp; wants</h2>
      <p class="sub mt-1">The AI looked at the last 6 months and found regular payments. Confirm what is a <b>need</b> (bills, school, loans) and what is a <b>want</b>, and set a monthly limit for wants. FinPilot judges purchases against this.</p>
      <div class="mt-5 overflow-x-auto">
        <table class="tbl"><thead><tr><th>Category</th><th>Usual / month</th><th>Need or want</th><th>Monthly limit</th></tr></thead>
        <tbody>${rows.map((r, i) => `
          <tr data-i="${i}">
            <td><div class="font-semibold">${esc(r.name)}</div><div class="text-xs text-slate-500">${esc(r.why)}</div></td>
            <td class="whitespace-nowrap">${money(r.usual_per_month)}</td>
            <td><div class="tabs" style="width:150px"><button type="button" class="tab ${r.kind === "need" ? "active" : ""}" data-kind="need">Need</button><button type="button" class="tab ${r.kind === "want" ? "active" : ""}" data-kind="want">Want</button></div></td>
            <td><input class="input" style="width:110px" type="number" min="0" step="10" value="${r.suggested_limit != null ? Math.round(r.suggested_limit) : ""}" ${r.kind === "need" ? "disabled" : ""} placeholder="${r.kind === "need" ? "—" : "no limit"}"></td>
          </tr>`).join("")}</tbody></table>
      </div>
      <div class="flex justify-end gap-2 mt-6"><button class="btn btn-ghost" id="setup-cancel">Later</button><button class="btn btn-primary" id="setup-save">Save</button></div>
    </div>`);
  $$("#modal-card tr[data-i]").forEach((tr) => $$("[data-kind]", tr).forEach((b) => b.addEventListener("click", () => {
    $$("[data-kind]", tr).forEach((x) => x.classList.toggle("active", x === b));
    const input = $("input", tr);
    input.disabled = b.dataset.kind === "need";
    if (input.disabled) input.value = "";
    else if (!input.value) input.value = Math.round(rows[tr.dataset.i].usual_per_month);
  })));
  $("#setup-cancel").addEventListener("click", closeModal);
  $("#setup-save").addEventListener("click", (e) => withBusy(e.currentTarget, async () => {
    const items = $$("#modal-card tr[data-i]").map((tr) => {
      const r = rows[tr.dataset.i];
      const kind = $("[data-kind].active", tr).dataset.kind;
      const v = $("input", tr).value;
      return { category: r.category, kind, monthly_limit: kind === "want" && v !== "" ? Number(v) : null };
    });
    await api("/api/setup", { method: "POST", body: { items } });
    closeModal();
    state.me = await api("/api/me");
    toast("Saved. FinPilot now judges purchases against your needs, wants and limits.");
    route();
  }));
}

// ------------------------------------------------------------------ Upcoming

ROUTES.upcoming = async (el) => {
  const u = await api("/api/upcoming?days=45");
  const byDay = {};
  u.items.forEach((i) => (byDay[i.date] = byDay[i.date] || []).push(i));
  const total = u.items.reduce((s, i) => s + -i.amount, 0);
  el.innerHTML = `
    ${header("Upcoming", `Regular payments found by ML and plans your family added · next 45 days · ${money(total)} in total`, `<button class="btn btn-primary" id="add-plan">+ Add a plan</button>`)}
    <div class="grid lg:grid-cols-3 gap-4">
      <section class="card lg:col-span-2">
        ${Object.entries(byDay).map(([d, items]) => `
          <div class="mb-4"><div class="timeline-day">${weekday(d)}</div>
          ${items.map((i) => `<div class="row-line">
            <div class="min-w-0"><div class="font-medium">${esc(i.name)} ${i.kind === "plan" ? '<span class="pill pill-blue">plan</span>' : ""}</div>
              <div class="text-xs text-slate-500">${esc(i.detail)}${i.member ? ` · ${esc(i.member)}` : ""}${i.category ? ` · ${esc(state.categories[i.category] || i.category)}` : ""}</div></div>
            <div class="flex items-center gap-2"><b>${money(-i.amount)}</b>${i.kind === "plan" ? `<button class="btn-icon" data-del-plan="${i.id}" title="Remove">&times;</button>` : ""}</div></div>`).join("")}</div>`).join("") || '<p class="sub">Nothing found.</p>'}
      </section>
      <section class="card">
        <h2 class="h2">Rest of this month</h2><p class="sub">${u.days_left} days left. What usually still goes out, by category (ML forecast).</p>
        <div class="mt-3">${u.rest_of_month.map((r) => `<div class="row-line"><div><div class="font-medium">${esc(r.name)}</div>${r.light ? `<span class="pill ${LIGHT[r.light].pill}">risk ${pct(r.risk)}</span>` : ""}</div><b>~${money(r.expected)}</b></div>`).join("")}</div>
      </section>
    </div>`;
  $("#add-plan").addEventListener("click", () => {
    modal(`<form class="p-6 space-y-4" id="plan-form"><h2 class="h1">Add a plan</h2><p class="sub">A one-off expense coming up: a birthday, a school trip, a repair.</p>
      <label class="field">What<input class="input" name="name" required placeholder="School trip"></label>
      <div class="grid grid-cols-2 gap-3"><label class="field">Amount, $<input class="input" name="amount" type="number" min="1" step="1" required></label>
      <label class="field">Date<input class="input" name="date" type="date" required></label></div>
      <div class="flex justify-end gap-2"><button type="button" class="btn btn-ghost" onclick="closeModal()">Cancel</button><button class="btn btn-primary">Add</button></div></form>`);
    $("#plan-form").addEventListener("submit", (e) => {
      e.preventDefault();
      const f = Object.fromEntries(new FormData(e.target));
      withBusy(e.target.querySelector(".btn-primary"), async () => {
        await api("/api/plans", { method: "POST", body: { name: f.name, amount: Number(f.amount), date: f.date } });
        closeModal(); route();
      });
    });
  });
  $$("[data-del-plan]").forEach((b) => b.addEventListener("click", async () => { await api(`/api/plans/${b.dataset.delPlan}`, { method: "DELETE" }); route(); }));
};

// ------------------------------------------------------------------ Goals

ROUTES.goals = async (el) => {
  const g = await api("/api/goals");
  const parent = state.me.member.role === "parent";
  el.innerHTML = `
    ${header("Goals", `The family keeps about ${money(g.free_cash_per_month)} a month. FinPilot shares it between family goals, nearest deadline first.`,
      `<button class="btn btn-primary" id="add-goal">+ New goal</button>`)}
    <h2 class="h2 mb-3">Family goals</h2>
    <div class="grid md:grid-cols-2 gap-4">${g.family.map((x) => goalCard(x, parent)).join("") || '<div class="card sub">No family goals yet.</div>'}</div>
    <h2 class="h2 mt-8 mb-3">Personal goals</h2>
    <div class="grid md:grid-cols-2 gap-4">${g.personal.map((x) => goalCard(x, x.mine || parent, x.owner)).join("") || '<div class="card sub">No personal goals yet.</div>'}</div>`;
  bindGoalButtons(el);
  $("#add-goal").addEventListener("click", () => goalForm(parent));
};

function goalForm(parent, personalOnly = false) {
  modal(`<form class="p-6 space-y-4" id="goal-form"><h2 class="h1">New goal</h2>
    <label class="field">Goal<input class="input" name="name" required placeholder="${personalOnly ? "Gaming PC" : "Kids' college fund"}"></label>
    <div class="grid grid-cols-3 gap-3"><label class="field">Target, $<input class="input" name="target" type="number" min="1" required></label>
    <label class="field">Saved, $<input class="input" name="saved" type="number" min="0" value="0"></label>
    <label class="field">Deadline<input class="input" name="deadline" type="date" required></label></div>
    ${parent && !personalOnly ? `<label class="field">Whose goal<select class="select" name="personal"><option value="false">Family goal</option><option value="true">My personal goal</option></select></label>` : ""}
    <div class="flex justify-end gap-2"><button type="button" class="btn btn-ghost" onclick="closeModal()">Cancel</button><button class="btn btn-primary">Save goal</button></div></form>`);
  $("#goal-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target));
    withBusy(e.target.querySelector(".btn-primary"), async () => {
      await api("/api/goals", { method: "POST", body: { name: f.name, target: Number(f.target), saved: Number(f.saved || 0), deadline: f.deadline,
        personal: personalOnly || !parent || f.personal === "true" } });
      closeModal(); route();
    });
  });
}

function bindGoalButtons(el) {
  $$("[data-goal-save]", el).forEach((b) => b.addEventListener("click", () => {
    modal(`<form class="p-6 space-y-4" id="save-form"><h2 class="h1">Add savings</h2><label class="field">Amount, $<input class="input" name="amount" type="number" step="1" required autofocus></label>
      <div class="flex justify-end gap-2"><button type="button" class="btn btn-ghost" onclick="closeModal()">Cancel</button><button class="btn btn-primary">Add</button></div></form>`);
    $("#save-form").addEventListener("submit", (e) => {
      e.preventDefault();
      withBusy(e.target.querySelector(".btn-primary"), async () => {
        await api(`/api/goals/${b.dataset.goalSave}/save`, { method: "POST", body: { amount: Number(new FormData(e.target).get("amount")) } });
        closeModal(); route();
      });
    });
  }));
  $$("[data-goal-del]", el).forEach((b) => b.addEventListener("click", async () => {
    if (!confirm("Delete this goal?")) return;
    try { await api(`/api/goals/${b.dataset.goalDel}`, { method: "DELETE" }); route(); } catch (e) { toast(e.message); }
  }));
}

// ------------------------------------------------------------------ My space

ROUTES.me = async (el) => {
  const parent = state.me.member.role === "parent";
  const params = new URLSearchParams(location.hash.split("?")[1] || "");
  const viewing = params.get("member");
  const s = await api(`/api/space${viewing ? `?member_id=${viewing}` : ""}`);
  const teens = (state.room.members || []).filter((m) => m.role === "teen");
  const own = s.member.id === state.me.member.id;
  const switcher = parent ? `<select class="select" id="space-switch" style="width:auto">
      <option value="">My space</option>${teens.map((t) => `<option value="${t.id}" ${String(t.id) === viewing ? "selected" : ""}>${esc(t.display_name)}'s space</option>`).join("")}</select>` : "";
  const isTeen = s.member.role === "teen";
  el.innerHTML = `
    ${header(own ? "My space" : `${esc(s.member.name)}'s space`, `Your own money and plans. ${esc(s.note)}`, switcher)}
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
      ${isTeen ? kpi("Allowance this month", money(s.allowance_this_month), s.member.allowance_amount ? `${money(s.member.allowance_amount)} per ${s.member.allowance_period}` : "not set") : kpi("Personal spending this month", money(s.spent_this_month))}
      ${kpi("Earned this month", money(s.earned_this_month), "job, gifts, selling")}
      ${isTeen ? kpi("Spent this month", money(s.spent_this_month)) : kpi("Payments this month", String(s.recent.filter((r) => r.date.startsWith(s.month)).length))}
      ${isTeen ? kpi("Left this month", money(s.left_this_month)) : kpi("Kept per month", money(s.saves_per_month), "last 3 months")}
    </div>
    <div class="grid lg:grid-cols-3 gap-4 mt-4">
      <section class="card lg:col-span-2">
        <div class="flex items-center justify-between flex-wrap gap-2"><h2 class="h2">My goals</h2>${own ? `<button class="btn btn-ghost btn-sm" id="my-goal">+ New personal goal</button>` : ""}</div>
        <div class="grid md:grid-cols-2 gap-3 mt-3">${s.goals.map((g) => goalCard(g, own || parent)).join("") || '<p class="sub">No personal goals yet.</p>'}</div>
      </section>
      <section class="card">
        <h2 class="h2">${own ? "Add money in or out" : "Allowance"}</h2>
        ${own ? `<div class="space-y-2 mt-3">
          <button class="btn btn-ghost w-full" id="add-income">+ I earned money</button>
          <button class="btn btn-ghost w-full" id="add-expense">− I spent cash</button>
          <a href="#/add" class="btn btn-ghost w-full">↑ Upload a receipt</a></div>` : ""}
        ${parent && isTeen ? `<form id="allow-form" class="mt-4 space-y-3 ${own ? "pt-4 border-t border-slate-100" : ""}">
          <div class="grid grid-cols-2 gap-2"><label class="field">Amount, $<input class="input" name="amount" type="number" min="0" step="1" value="${s.member.allowance_amount ?? ""}"></label>
          <label class="field">Every<select class="select" name="period"><option value="week" ${s.member.allowance_period === "week" ? "selected" : ""}>week</option><option value="month" ${s.member.allowance_period === "month" ? "selected" : ""}>month</option></select></label></div>
          <button class="btn btn-ghost w-full">Save allowance</button>
          <div class="grid grid-cols-2 gap-2"><button type="button" class="btn btn-primary" id="pay-allow">Pay now</button><button type="button" class="btn btn-ghost" id="pay-allow-pp" title="${esc(s.member.paypal_email || "Add a PayPal sandbox email in Settings")}">Pay via PayPal</button></div>
          <p class="text-xs text-slate-500">PayPal uses Sandbox test money only.</p></form>` : ""}
      </section>
    </div>
    <div class="grid lg:grid-cols-3 gap-4 mt-4">
      <section class="card"><h2 class="h2">Where my money goes</h2><p class="sub">This month</p>
        <div class="mt-3">${s.by_category.map((c) => `<div class="row-line"><span>${esc(c.name)}</span><b>${money(c.spent)}</b></div>`).join("") || '<p class="sub">No spending yet this month.</p>'}</div></section>
      <section class="card lg:col-span-2"><h2 class="h2">Recent</h2>
        <div class="mt-2">${s.recent.slice(0, 12).map((r) => `<div class="row-line"><div class="min-w-0"><div class="font-medium truncate">${esc(r.description)}</div><div class="text-xs text-slate-500">${fmtDate(r.date)} · ${esc(state.categories[r.category] || r.category)}${r.source === "allowance" ? " · allowance" : ""}</div></div><b class="${r.amount > 0 ? "text-green-700" : ""}">${money(r.amount, 2)}</b></div>`).join("") || '<p class="sub">Nothing yet.</p>'}</div></section>
    </div>`;
  $("#space-switch")?.addEventListener("change", (e) => { location.hash = e.target.value ? `#/me?member=${e.target.value}` : "#/me"; });
  bindGoalButtons(el);
  $("#my-goal")?.addEventListener("click", () => goalForm(parent, true));
  const moneyForm = (title, url, sign) => {
    modal(`<form class="p-6 space-y-4" id="money-form"><h2 class="h1">${title}</h2>
      <label class="field">What<input class="input" name="description" required placeholder="${sign > 0 ? "Babysitting" : "Lunch with friends"}"></label>
      <div class="grid grid-cols-2 gap-3"><label class="field">Amount, $<input class="input" name="amount" type="number" min="0.5" step="0.01" required></label>
      <label class="field">Date<input class="input" name="date" type="date" value="${new Date().toISOString().slice(0, 10)}"></label></div>
      <div class="flex justify-end gap-2"><button type="button" class="btn btn-ghost" onclick="closeModal()">Cancel</button><button class="btn btn-primary">Save</button></div></form>`);
    $("#money-form").addEventListener("submit", (e) => {
      e.preventDefault();
      const f = Object.fromEntries(new FormData(e.target));
      withBusy(e.target.querySelector(".btn-primary"), async () => { await api(url, { method: "POST", body: { description: f.description, amount: Number(f.amount), date: f.date } }); closeModal(); route(); });
    });
  };
  $("#add-income")?.addEventListener("click", () => moneyForm("I earned money", "/api/space/income", 1));
  $("#add-expense")?.addEventListener("click", () => moneyForm("I spent cash", "/api/space/expense", -1));
  $("#allow-form")?.addEventListener("submit", (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target));
    withBusy(e.target.querySelector("button:not([type])"), async () => {
      await api(`/api/members/${s.member.id}`, { method: "PUT", body: { allowance_amount: Number(f.amount || 0), allowance_period: f.period } });
      toast("Allowance saved."); await refreshRoom(); route();
    });
  });
  const pay = (via) => (e) => withBusy(e.currentTarget, async () => {
    const r = await api("/api/allowance/pay", { method: "POST", body: { member_id: s.member.id, via_paypal: via } });
    toast(`Paid ${money(r.amount)} to ${s.member.name}${r.paypal ? " via PayPal Sandbox" : ""}.`); route();
  });
  $("#pay-allow")?.addEventListener("click", pay(false));
  $("#pay-allow-pp")?.addEventListener("click", pay(true));
};

// ------------------------------------------------------------------ Transactions

ROUTES.transactions = async (el) => {
  const params = new URLSearchParams(location.hash.split("?")[1] || "");
  const q = { category: params.get("category") || "", member_id: params.get("member") || "", q: params.get("q") || "" };
  const qs = new URLSearchParams(Object.entries({ limit: 200, ...q }).filter(([, v]) => v !== "")).toString();
  const t = await api(`/api/transactions?${qs}`);
  state.categories = t.categories;
  const catOpts = Object.entries(t.categories).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("");
  el.innerHTML = `
    ${header("Transactions", "Everyone's payments in one place. The AI sets each category; fix one and FinPilot fixes every payment from that merchant and learns from it.")}
    <div class="card card-tight mb-4 grid md:grid-cols-4 gap-3">
      <input class="input md:col-span-2" id="f-q" placeholder="Search description" value="${esc(q.q)}">
      <select class="select" id="f-member"><option value="">Everyone</option>${Object.entries(t.members).map(([id, n]) => `<option value="${id}" ${id === q.member_id ? "selected" : ""}>${esc(n)}</option>`).join("")}</select>
      <select class="select" id="f-cat"><option value="">All categories</option>${catOpts}</select>
    </div>
    <div class="card p-0 overflow-x-auto"><table class="tbl"><thead><tr><th>Date</th><th>Description</th><th>Who</th><th class="text-right">Amount</th><th>Category</th></tr></thead>
      <tbody>${t.transactions.map((x) => `<tr>
        <td class="whitespace-nowrap text-slate-500">${fmtDate(x.date)}</td>
        <td><div class="max-w-md truncate" title="${esc(x.description)}">${esc(x.description)}</div><div class="text-xs text-slate-400">${{ demo: "Bank (demo)", paypal: "PayPal Sandbox", upload: "Uploaded file", manual: "Added by hand", allowance: "Allowance" }[x.source] || x.source}</div></td>
        <td class="whitespace-nowrap">${esc(x.member || "")}</td>
        <td class="text-right whitespace-nowrap font-medium ${x.amount > 0 ? "text-green-700" : ""}">${money(x.amount, 2)}</td>
        <td class="whitespace-nowrap"><select class="tx-cat" data-tx="${esc(x.id)}">${Object.entries(t.categories).map(([k, v]) => `<option value="${k}" ${k === x.category ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>
          <span class="text-xs ${x.category_source === "user" ? "text-teal-700 font-semibold" : "text-slate-400"}">${x.category_source === "user" ? "you" : x.category_source === "file" ? "file" : "AI"}</span></td></tr>`).join("")}</tbody></table></div>
    <p class="sub mt-3" id="tx-msg">${t.transactions.length} shown</p>`;
  $("#f-cat").value = q.category;
  const go = () => {
    const p = new URLSearchParams(Object.entries({ q: $("#f-q").value.trim(), member: $("#f-member").value, category: $("#f-cat").value }).filter(([, v]) => v));
    location.hash = `#/transactions${p.toString() ? "?" + p : ""}`;
  };
  $("#f-member").addEventListener("change", go);
  $("#f-cat").addEventListener("change", go);
  $("#f-q").addEventListener("keydown", (e) => { if (e.key === "Enter") go(); });
  $$("[data-tx]").forEach((s) => s.addEventListener("change", async () => {
    try {
      const r = await api(`/api/transactions/${encodeURIComponent(s.dataset.tx)}/category`, { method: "POST", body: { category: s.value } });
      toast(`Saved. Also updated ${r.updated_same_merchant} other payment(s) from this merchant; the AI is learning from your fix.`, 5000);
      route();
    } catch (e) { toast(e.message); }
  }));
};

// ------------------------------------------------------------------ Add data

ROUTES.add = async (el) => {
  const room = state.room;
  const me = room.members.find((m) => m.id === state.me.member.id);
  el.innerHTML = `
    ${header("Add data", "Bring in your money. Everything you add is yours in the room, and also counts in the family's totals.")}
    <div class="grid lg:grid-cols-3 gap-4">
      <section class="card lg:col-span-2">
        <div class="flex items-center gap-2"><h2 class="h2">Upload a receipt, statement or table</h2><span class="pill pill-blue">Gemini</span></div>
        <p class="sub">Photo of a receipt (JPG, PNG, HEIC), a bank statement PDF, or a CSV/Excel file. Gemini reads it, our model sorts each line into a category, you check before importing.</p>
        <label class="dropzone block mt-4" id="drop">
          <input type="file" id="file" class="hidden" accept="image/*,.pdf,.csv,.xlsx,.xls">
          <div class="text-3xl">⬆</div><div class="font-semibold mt-2">Drop a file here or click to choose</div><div class="sub">Up to 15 MB</div>
        </label>
        <div id="upload-result" class="mt-4"></div>
      </section>
      <section class="space-y-4">
        <div class="card">
          <div class="flex items-center gap-2"><h2 class="h2">PayPal</h2><span class="pill pill-gray">Sandbox</span></div>
          <p class="sub">Card and PayPal payments from the test account. Payments go to the family member whose PayPal email matches.</p>
          <label class="field mt-3">My PayPal (sandbox) email<input class="input" id="pp-email" type="email" value="${esc(me?.paypal_email || "")}" placeholder="me@personal.example.com"></label>
          <div class="flex gap-2 mt-3"><button class="btn btn-ghost" id="pp-save">Save email</button><button class="btn btn-primary" id="pp-sync" ${room.paypal_configured ? "" : "disabled title='PayPal keys missing in .env'"}>Sync PayPal</button></div>
        </div>
        ${room.is_demo ? `<div class="card"><h2 class="h2">Demo room</h2><p class="sub">Start the Carter family over from scratch (deletes changes made in the demo).</p><button class="btn btn-danger mt-3" id="demo-reset">Reset demo</button></div>` : ""}
      </section>
    </div>`;
  const drop = $("#drop");
  ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("drag"); }));
  drop.addEventListener("drop", (e) => e.dataTransfer.files[0] && uploadFile(e.dataTransfer.files[0]));
  $("#file").addEventListener("change", (e) => e.target.files[0] && uploadFile(e.target.files[0]));
  $("#pp-save").addEventListener("click", (e) => withBusy(e.currentTarget, async () => {
    await api(`/api/members/${state.me.member.id}`, { method: "PUT", body: { paypal_email: $("#pp-email").value } });
    await refreshRoom(); toast("PayPal email saved.");
  }));
  $("#pp-sync").addEventListener("click", (e) => withBusy(e.currentTarget, async () => {
    const r = await api("/api/paypal/sync", { method: "POST" });
    toast(`Imported ${r.imported} PayPal transaction(s)` + (Object.keys(r.by_member).length ? `: ${Object.entries(r.by_member).map(([n, c]) => `${n} ${c}`).join(", ")}` : ""), 5000);
  }));
  $("#demo-reset")?.addEventListener("click", async () => {
    if (!confirm("Reset the demo family? All changes in the demo room will be deleted.")) return;
    await api("/api/demo/reset", { method: "POST" });
    await api(`/api/demo/login?who=alex`, { method: "POST" });
    await boot();
  });
};

async function uploadFile(file) {
  const box = $("#upload-result");
  box.innerHTML = `<div class="flex items-center gap-3 sub"><span class="spinner spinner-dark"></span> Gemini is reading “${esc(file.name)}”…</div>`;
  const fd = new FormData();
  fd.append("file", file);
  let r;
  try { r = await api("/api/uploads", { method: "POST", body: fd }); } catch (e) { box.innerHTML = `<div class="text-red-700 text-sm">${esc(e.message)}</div>`; return; }
  const cats = Object.entries(r.categories);
  box.innerHTML = `
    <div class="flex items-center justify-between flex-wrap gap-2"><div class="font-semibold">Found ${r.rows.length} line(s) · ${esc(r.document_type)}</div><span class="text-xs text-slate-500">Check and fix before importing</span></div>
    <div class="overflow-x-auto mt-2"><table class="tbl"><thead><tr><th>Date</th><th>Description</th><th>Amount</th><th>Category</th><th></th></tr></thead><tbody>
      ${r.rows.map((x, i) => `<tr data-row="${i}">
        <td><input class="input" style="width:140px" type="date" value="${esc(x.date)}" data-k="date"></td>
        <td><input class="input" value="${esc(x.description)}" data-k="description">${x.items?.length ? `<div class="text-xs text-slate-400 mt-1">${esc(x.items.join(", "))}</div>` : ""}</td>
        <td><input class="input" style="width:110px" type="number" step="0.01" value="${x.amount}" data-k="amount"></td>
        <td><select class="select" data-k="category">${cats.map(([k, v]) => `<option value="${k}" ${k === x.category ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></td>
        <td><button class="btn-icon" data-remove="${i}" title="Remove">&times;</button></td></tr>`).join("")}
    </tbody></table></div>
    <div class="flex justify-end gap-2 mt-3"><button class="btn btn-primary" id="import">Import</button></div>`;
  $$("[data-remove]", box).forEach((b) => b.addEventListener("click", () => b.closest("tr").remove()));
  $("#import").addEventListener("click", (e) => withBusy(e.currentTarget, async () => {
    const rows = $$("tr[data-row]", box).map((tr) => Object.fromEntries($$("[data-k]", tr).map((i) => [i.dataset.k, i.value])));
    const res = await api(`/api/uploads/${r.upload_id}/confirm`, { method: "POST", body: { rows } });
    box.innerHTML = `<div class="text-green-700 font-semibold">Imported ${res.imported} transaction(s). <a class="link" href="#/transactions">See them</a></div>`;
  }));
}

// ------------------------------------------------------------------ Check a purchase

ROUTES.check = async (el) => {
  el.innerHTML = `
    ${header("Check a purchase", "The same check the Chrome extension runs on any product page. It uses the family budget, your usual prices and market prices.")}
    <form id="check-form" class="card grid md:grid-cols-6 gap-3 items-end">
      <label class="field md:col-span-3">Product<input class="input" name="title" value="Sony WH-1000XM5 Wireless Noise Canceling Headphones" required></label>
      <label class="field">Price, $<input class="input" name="price" type="number" min="1" step="0.01" value="348" required></label>
      <label class="field md:col-span-2">Store link (optional)<input class="input" name="url" value="https://www.amazon.com/dp/B09XS7JWHH"></label>
      <div class="md:col-span-6 flex flex-wrap gap-2 justify-between items-center">
        <div class="flex flex-wrap gap-2 text-xs">${[["Concert tickets", 100, "https://www.ticketmaster.com/event/1"], ["Graphing calculator for school", 129, "https://www.amazon.com/dp/1"], ["Water bottle 32 oz", 24, "https://www.amazon.com/dp/2"]]
          .map(([t, p, u]) => `<button type="button" class="suggestion" data-ex='${esc(JSON.stringify([t, p, u]))}'>${esc(t)} · $${p}</button>`).join("")}</div>
        <button class="btn btn-primary">Check</button></div>
    </form>
    <div id="verdict" class="mt-4"></div>`;
  $$("[data-ex]").forEach((b) => b.addEventListener("click", () => {
    const [t, p, u] = JSON.parse(b.dataset.ex);
    const f = $("#check-form");
    f.elements.namedItem("title").value = t;
    f.elements.namedItem("price").value = p;
    f.elements.namedItem("url").value = u;
    f.requestSubmit();
  }));
  $("#check-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target));
    const body = { title: f.title, price: Number(f.price), url: f.url };
    $("#verdict").innerHTML = `<div class="card flex items-center gap-3 sub"><span class="spinner spinner-dark"></span> Checking budget, usual prices and market prices…</div>`;
    api("/api/check-purchase", { method: "POST", body }).then((r) => renderVerdict($("#verdict"), r, body)).catch((err) => { $("#verdict").innerHTML = `<div class="card text-red-700">${esc(err.message)}</div>`; });
  });
};

function renderVerdict(box, r, body) {
  const d = DECISION[r.decision];
  const m = r.market;
  let scale = "";
  if (m) {
    const lo = Math.min(m.low, r.price) * 0.7, hi = Math.max(m.high, r.price) * 1.15;
    const pos = (x) => Math.max(0, Math.min(100, ((x - lo) / (hi - lo)) * 100));
    scale = `<div class="mt-5"><div class="label mb-2">Market price of similar items (2023 prices)</div>
      <div class="price-scale"><div class="price-marker" style="left:calc(${pos(r.price)}% - 2px)"></div></div>
      <div class="flex justify-between text-xs text-slate-500 mt-1.5"><span>Similar items: ${money(m.low)}–${money(m.high)}</span><span>This: <b>${money(r.price, 2)}</b></span></div>
      <div class="text-xs text-slate-400 mt-1">Our price model${m.gemini ? " + Gemini" : ""} · ${esc(m.source)}</div></div>`;
  }
  box.innerHTML = `
    <div class="verdict verdict-${r.decision} bg-white">
      <div class="verdict-head">
        <div class="flex items-start justify-between gap-3 flex-wrap">
          <div><div class="text-2xl font-extrabold">${d.icon} ${esc(r.title_text)}</div>
            <div class="sub mt-1">${esc(r.title || "This item")} · <b>${money(r.price, 2)}</b> · ${esc(r.category_name)} (${esc(r.kind)})</div></div>
          ${r.reasonable_price ? `<div class="text-right"><div class="label">Reasonable price for you</div><div class="text-2xl font-extrabold">up to ${money(r.reasonable_price)}</div></div>`
            : r.no_room_this_month ? `<div class="text-right"><div class="label">This month</div><div class="font-bold">No room in the ${esc(r.category_name)} budget</div><div class="text-xs text-slate-500">fresh month from ${fmtDate(r.next_month_starts)}</div></div>` : ""}
        </div>
      </div>
      <div class="p-5">
        <ul class="space-y-2">${r.reasons.map((x) => `<li class="flex gap-2"><span>•</span><span>${esc(x)}</span></li>`).join("")}</ul>
        ${r.risk_after != null ? `<div class="mt-5"><div class="label mb-2">Chance of overspending ${esc(r.category_name)} this month: ${pct(r.risk_before)} → <b>${pct(r.risk_after)}</b></div>
          <div class="bar"><div style="width:${Math.round(r.risk_after * 100)}%;background:${r.risk_after >= 0.75 ? "var(--red)" : r.risk_after >= 0.44 ? "var(--yellow)" : "var(--green)"}"></div></div>
          ${r.budget ? `<div class="text-xs text-slate-500 mt-1.5">Spent ${money(r.spent_this_month)} of ${money(r.budget)} so far this month</div>` : ""}</div>` : ""}
        ${scale}
        <div class="flex flex-wrap gap-2 mt-6 items-center">
          ${r.decision !== "buy" ? `<button class="btn btn-primary" id="v-postpone">Postpone</button>` : ""}
          <button class="btn btn-ghost" id="v-ask">Ask the assistant</button>
          <span class="text-xs text-slate-500">Checked for ${esc(r.checked_for)} · uses the ${esc(r.uses)} · ${esc(r.disclaimer)}</span>
        </div>
      </div>
    </div>`;
  $("#v-postpone")?.addEventListener("click", (e) => withBusy(e.currentTarget, async () => {
    const res = await api("/api/postpone", { method: "POST", body: { ...body, category: r.category, decision: r.decision, probability: r.risk_after } });
    toast(`Postponed. Reminder on ${fmtDate(res.remind_on)}.`);
  }));
  $("#v-ask").addEventListener("click", () => { openChat(); sendChat("What if I wait until next month?", { title: body.title, price: body.price, url: body.url, category: r.category }); });
}

// ------------------------------------------------------------------ Postponed

ROUTES.postponed = async (el) => {
  const p = await api("/api/postponed");
  el.innerHTML = `
    ${header("Postponed", `${money(p.waiting_total)} waiting · ${money(p.not_bought_total)} kept by deciding not to buy`)}
    <div class="card">${p.items.map((i) => `<div class="row-line">
      <div class="min-w-0"><div class="font-semibold truncate">${i.url ? `<a class="hover:underline" href="${esc(i.url)}" target="_blank" rel="noopener">${esc(i.title)}</a>` : esc(i.title)}</div>
        <div class="text-xs text-slate-500">${esc(i.member || "")} · ${esc(state.categories[i.category] || i.category || "")} · postponed ${fmtDate(i.created_at.slice(0, 10))} · reminder ${i.remind_on ? fmtDate(i.remind_on) : "—"}${i.probability != null ? ` · risk was ${pct(i.probability)}` : ""}</div></div>
      <div class="flex items-center gap-2"><b>${money(i.price, 2)}</b>
        ${i.status === "waiting" ? `<button class="btn btn-ghost btn-sm" data-pp="${i.id}" data-st="bought">Bought</button><button class="btn btn-ghost btn-sm" data-pp="${i.id}" data-st="dropped">Don't need it</button>`
          : `<span class="pill ${i.status === "dropped" ? "pill-green" : "pill-gray"}">${i.status === "dropped" ? "Kept the money" : "Bought"}</span>`}</div></div>`).join("")
      || '<p class="sub">Nothing postponed yet. When FinPilot says “Not worth it”, press Postpone and the item waits here with a reminder.</p>'}</div>`;
  $$("[data-pp]").forEach((b) => b.addEventListener("click", async () => { await api(`/api/postponed/${b.dataset.pp}`, { method: "PATCH", body: { status: b.dataset.st } }); route(); }));
};

// ------------------------------------------------------------------ Settings

ROUTES.settings = async (el) => {
  await refreshRoom();
  const r = state.room;
  const parent = state.me.member.role === "parent";
  el.innerHTML = `
    ${header("Settings", esc(r.room_name))}
    <div class="grid lg:grid-cols-3 gap-4">
      <section class="card lg:col-span-2">
        <h2 class="h2">Family members</h2>
        <div class="mt-3">${r.members.map((m, i) => `<div class="row-line">
          <div class="flex items-center gap-3 min-w-0">${avatar(m.display_name, i)}<div class="min-w-0"><div class="font-semibold">${esc(m.display_name)} <span class="pill ${m.role === "parent" ? "pill-teal" : "pill-blue"}">${m.role}</span></div>
            <div class="text-xs text-slate-500 truncate">${esc(m.email)} · ${m.transactions} transactions${m.paypal_email ? ` · PayPal ${esc(m.paypal_email)}` : ""}${m.allowance_amount ? ` · allowance ${money(m.allowance_amount)}/${m.allowance_period}` : ""}</div></div></div>
          ${m.role === "teen" && parent ? `<a class="btn btn-ghost btn-sm" href="#/me?member=${m.id}">Open space</a>` : ""}</div>`).join("")}</div>
      </section>
      <section class="space-y-4">
        <div class="card"><h2 class="h2">Invite family</h2><p class="sub">Share this code. Teens and the other parent sign up and choose “Join with a code”.</p>
          <button class="room-code text-base mt-3" id="code-big">${esc(r.room_code)}</button></div>
        <div class="card"><h2 class="h2">Needs &amp; wants</h2><p class="sub">What counts as a need, and monthly limits for wants.</p>
          <button class="btn btn-ghost mt-3" id="re-setup" ${parent ? "" : "disabled title='Parents only'"}>Review</button></div>
        <div class="card"><h2 class="h2">Connections</h2>
          <div class="row-line"><span>PayPal Sandbox</span><span class="pill ${r.paypal_configured ? "pill-green" : "pill-gray"}">${r.paypal_configured ? "keys found" : "no keys"}</span></div>
          <div class="row-line"><span>Gemini (uploads, prices)</span><span class="pill ${r.gemini_configured ? "pill-green" : "pill-gray"}">${r.gemini_configured ? "key found" : "no key"}</span></div>
          <p class="text-xs text-slate-500 mt-2">Keys live in the .env file on this computer.</p></div>
      </section>
    </div>`;
  $("#code-big").addEventListener("click", () => { navigator.clipboard?.writeText(r.room_code); toast("Invite code copied."); });
  $("#re-setup").addEventListener("click", openSetup);
};

// ------------------------------------------------------------------ Assistant

function addMsg(text, who) {
  const div = document.createElement("div");
  div.className = who === "user" ? "msg-user" : "msg-bot";
  div.textContent = text;
  $("#chat-log").appendChild(div);
  $("#chat-log").scrollTop = $("#chat-log").scrollHeight;
  return div;
}
function openChat() {
  $("#chat").classList.remove("hidden");
  if (!$("#chat-log").children.length) addMsg(`Hi ${state.me.user.name.split(" ")[0]}! Ask me about the family's spending, upcoming bills, goals, or whether something is worth buying.`, "bot");
  $("#chat-input").focus();
}
async function sendChat(text, context) {
  addMsg(text, "user");
  const pending = addMsg("…", "bot");
  try {
    const r = await api("/api/chat", { method: "POST", body: { message: text, context } });
    pending.textContent = r.reply;
  } catch (e) { pending.textContent = e.message; }
  $("#chat-log").scrollTop = $("#chat-log").scrollHeight;
}
$("#chat-toggle").addEventListener("click", () => ($("#chat").classList.contains("hidden") ? openChat() : $("#chat").classList.add("hidden")));
$("#chat-close").addEventListener("click", () => $("#chat").classList.add("hidden"));
$("#chat-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const t = $("#chat-input").value.trim();
  if (!t) return;
  $("#chat-input").value = "";
  sendChat(t);
});
$("#chat-suggestions").innerHTML = ["What bills are coming up?", "Can I buy concert tickets for $100?", "How much did we spend on dining?", "Where are we losing money?"]
  .map((s) => `<button class="suggestion">${esc(s)}</button>`).join("");
$$("#chat-suggestions .suggestion").forEach((b) => b.addEventListener("click", () => sendChat(b.textContent)));

// ------------------------------------------------------------------ boot

async function refreshRoom() { state.room = await api("/api/room"); }

async function boot() {
  try {
    state.me = await api("/api/me");
  } catch (e) {
    return showAuth();
  }
  if (!state.me.member) { showAuth(); return renderAuthCard("room"); }
  await refreshRoom();
  try { state.categories = (await api("/api/transactions?limit=1")).categories; } catch (e) { /* empty room */ }
  renderShell();
  route();
}

boot();
