// FinPilot website: talks to the FastAPI backend on the same origin.
const $ = (sel) => document.querySelector(sel);
const money = (x, digits = 0) =>
  (x < 0 ? "−$" : "$") + Math.abs(x).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
const pct = (p) => (p == null ? "—" : Math.round(p * 100) + "%");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

let CATEGORY_NAMES = {};
let trendChart = null;

async function api(path, options = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `Request failed (${res.status})`);
  return body;
}

function toast(text) {
  const t = $("#toast");
  t.textContent = text;
  t.classList.remove("hidden");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.add("hidden"), 3500);
}

const LIGHT = {
  red: { pill: "pill-red", label: "High risk", color: "var(--red)" },
  yellow: { pill: "pill-yellow", label: "Watch", color: "var(--yellow)" },
  green: { pill: "pill-green", label: "On track", color: "var(--green)" },
};

// ---------- status and data sources ----------

async function loadStatus() {
  const s = await api("/api/status");
  const sources = [];
  if (s.profile.data_source === "demo") sources.push('<span class="pill pill-gray">Demo family</span>');
  if (s.profile.paypal_connected === "yes") sources.push('<span class="pill pill-green">PayPal Sandbox ✓</span>');
  $("#sources").innerHTML = sources.join(" ");
  if (s.profile.family_name) $("#family-name").textContent = s.profile.family_name;
  $("#btn-refresh-paypal").classList.toggle("hidden", !s.paypal_configured);
  return s;
}

async function importSource(kind, msgEl) {
  if (msgEl) msgEl.textContent = kind === "demo" ? "Loading the demo family…" : "Connecting to PayPal Sandbox…";
  try {
    const r = await api(`/api/import/${kind}`, { method: "POST" });
    toast(`Imported ${r.imported} transactions from ${kind === "demo" ? "the demo family" : "PayPal Sandbox"}`);
    await refreshAll();
  } catch (e) {
    if (msgEl) msgEl.textContent = e.message;
    toast(e.message);
  }
}

// ---------- dashboard ----------

function renderKpis(s) {
  const items = [
    ["Spent this month", money(s.spent_this_month)],
    ["Income this month", money(s.income_this_month)],
    ["Free cash / month", money(s.free_cash_per_month), "average of the last 6 months"],
    ["Days left", s.days_left, s.month],
  ];
  $("#kpis").innerHTML = items
    .map(([label, value, hint]) => `<div class="kpi"><div class="label">${label}</div><div class="value">${value}</div>${hint ? `<div class="text-xs text-slate-400">${hint}</div>` : ""}</div>`)
    .join("");
}

function renderCategories(cats) {
  const sorted = [...cats].sort((a, b) => (b.overspend_probability ?? -1) - (a.overspend_probability ?? -1));
  $("#categories").innerHTML = sorted
    .map((c) => {
      const l = LIGHT[c.light];
      const ratio = c.budget ? Math.max(0, Math.min(1.2, c.spent / c.budget)) : 0;
      const pill = l ? `<span class="pill ${l.pill}">${l.label} · ${pct(c.overspend_probability)}</span>` : '<span class="pill pill-gray">Not enough history</span>';
      return `
      <div>
        <div class="flex items-center justify-between gap-2 text-sm">
          <div class="font-medium">${esc(c.name)}</div>
          <div class="flex items-center gap-2">
            <span class="text-slate-500">${money(c.spent)} of
              <button class="underline decoration-dotted" data-budget="${c.category}" title="Set your own budget">${c.budget ? money(c.budget) : "—"}</button>
            </span>${pill}
          </div>
        </div>
        <div class="bar mt-1.5"><div style="width:${(ratio / 1.2) * 100}%; background:${l ? l.color : "#94a3b8"}"></div></div>
      </div>`;
    })
    .join("");
  document.querySelectorAll("[data-budget]").forEach((b) =>
    b.addEventListener("click", async () => {
      const cat = b.dataset.budget;
      const value = prompt(`Monthly budget for ${CATEGORY_NAMES[cat] || cat} in $ (leave empty to use your usual level):`);
      if (value === null) return;
      const amount = value.trim() === "" ? null : Number(value);
      if (amount !== null && !(amount >= 0)) return toast("Please enter a number");
      await api(`/api/budgets/${cat}`, { method: "PUT", body: JSON.stringify({ amount }) });
      toast("Budget saved");
      await loadSummary();
    })
  );
}

function renderTrend(trend) {
  const cats = ["housing", "groceries", "dining", "shopping", "transportation", "utilities", "subscriptions", "entertainment", "insurance", "health"];
  const colors = ["#0f766e", "#14b8a6", "#f59e0b", "#6366f1", "#0ea5e9", "#94a3b8", "#ec4899", "#a855f7", "#64748b", "#22c55e"];
  const datasets = cats
    .map((c, i) => ({ label: CATEGORY_NAMES[c] || c, data: trend.map((r) => Math.max(0, r[c] || 0)), backgroundColor: colors[i] }))
    .filter((d) => d.data.some((v) => v > 0));
  if (trendChart) trendChart.destroy();
  trendChart = new Chart($("#trend"), {
    type: "bar",
    data: { labels: trend.map((r) => r.month), datasets },
    options: {
      maintainAspectRatio: false,
      plugins: { legend: { position: "bottom", labels: { boxWidth: 10, font: { size: 11 } } } },
      scales: { x: { stacked: true, grid: { display: false } }, y: { stacked: true, ticks: { callback: (v) => "$" + v / 1000 + "k" } } },
    },
  });
}

function renderGoals(goals, freeCash) {
  $("#free-cash-label").textContent = `You keep about ${money(freeCash)} a month after spending. FinPilot shares it between goals, nearest deadline first.`;
  if (!goals.length) {
    $("#goal-list").innerHTML = '<div class="card text-slate-500">No goals yet. Add one: a college fund, a car, a home.</div>';
    return;
  }
  $("#goal-list").innerHTML = goals
    .map(
      (g) => `
    <div class="card">
      <div class="flex items-start justify-between gap-2">
        <div>
          <div class="font-semibold">${esc(g.name)}</div>
          <div class="text-sm text-slate-500">${money(g.saved)} of ${money(g.target)} · by ${g.deadline}</div>
        </div>
        <span class="pill ${g.on_track ? "pill-green" : "pill-red"}">${g.on_track ? "On track" : "Behind"}</span>
      </div>
      <div class="bar mt-3"><div style="width:${Math.min(100, g.progress * 100)}%; background:var(--brand)"></div></div>
      <div class="grid grid-cols-3 gap-2 mt-3 text-sm">
        <div><div class="text-slate-500 text-xs">Needs / month</div><div class="font-medium">${money(g.needed_per_month)}</div></div>
        <div><div class="text-slate-500 text-xs">Gets now</div><div class="font-medium">${money(g.allocated_per_month)}</div></div>
        <div><div class="text-slate-500 text-xs">Reached</div><div class="font-medium">${esc(g.projected_date)}</div></div>
      </div>
      <div class="flex gap-2 mt-3">
        <button class="btn-small" data-goal-add="${g.id}">+ Add savings</button>
        <button class="btn-small" data-goal-del="${g.id}">Delete</button>
      </div>
    </div>`
    )
    .join("");
  document.querySelectorAll("[data-goal-add]").forEach((b) =>
    b.addEventListener("click", async () => {
      const g = goals.find((x) => x.id == b.dataset.goalAdd);
      const value = prompt(`How much did you add to "${g.name}"? ($)`);
      if (!value || !(Number(value) > 0)) return;
      await api(`/api/goals/${g.id}`, { method: "PUT", body: JSON.stringify({ name: g.name, target: g.target, saved: g.saved + Number(value), deadline: g.deadline }) });
      await loadSummary();
    })
  );
  document.querySelectorAll("[data-goal-del]").forEach((b) =>
    b.addEventListener("click", async () => {
      if (!confirm("Delete this goal?")) return;
      await api(`/api/goals/${b.dataset.goalDel}`, { method: "DELETE" });
      await loadSummary();
    })
  );
}

async function loadSummary() {
  const s = await api("/api/summary");
  $("#month-label").textContent = `${s.today} · ${s.days_left} days left in the month`;
  renderKpis(s);
  renderCategories(s.categories);
  renderTrend(s.trend);
  const other = Object.entries(s.other_spending).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
  $("#other-spending").innerHTML = other.length
    ? "Bills this month: " + other.map(([c, v]) => `${esc(CATEGORY_NAMES[c] || c)} ${money(v)}`).join(" · ")
    : "";
  renderGoals(s.goals, s.free_cash_per_month);
}

// ---------- postponed ----------

async function loadPostponed() {
  const p = await api("/api/postponed");
  const waiting = p.items.filter((i) => i.status === "waiting");
  $("#postponed-label").textContent = waiting.length
    ? `${waiting.length} waiting · ${money(p.waiting_total)} not spent yet${p.not_bought_total ? ` · ${money(p.not_bought_total)} you decided not to buy` : ""}`
    : "Nothing postponed yet. When the extension says “better wait”, click Postpone and it shows up here.";
  if (!p.items.length) {
    $("#postponed-list").innerHTML = '<div class="text-slate-500 text-sm">Empty for now.</div>';
    return;
  }
  $("#postponed-list").innerHTML = `<div class="divide-y divide-slate-100">${p.items
    .map(
      (i) => `
    <div class="py-3 flex items-center justify-between gap-3">
      <div class="min-w-0">
        <div class="font-medium truncate">${i.url ? `<a class="hover:underline" href="${esc(i.url)}" target="_blank" rel="noopener">${esc(i.title || "Item")}</a>` : esc(i.title || "Item")}</div>
        <div class="text-xs text-slate-500">${esc(CATEGORY_NAMES[i.category] || i.category || "")} · postponed ${i.created_at.slice(0, 10)} · reminder ${i.remind_on || "—"}${i.probability != null ? ` · risk was ${pct(i.probability)}` : ""}</div>
      </div>
      <div class="flex items-center gap-2">
        <span class="font-semibold">${money(i.price, 2)}</span>
        ${
          i.status === "waiting"
            ? `<button class="btn-small" data-pp="${i.id}" data-status="bought">Bought</button><button class="btn-small" data-pp="${i.id}" data-status="dropped">Not needed</button>`
            : `<span class="pill ${i.status === "dropped" ? "pill-green" : "pill-gray"}">${i.status === "dropped" ? "Saved" : "Bought"}</span>`
        }
      </div>
    </div>`
    )
    .join("")}</div>`;
  document.querySelectorAll("[data-pp]").forEach((b) =>
    b.addEventListener("click", async () => {
      await api(`/api/postponed/${b.dataset.pp}`, { method: "PATCH", body: JSON.stringify({ status: b.dataset.status }) });
      await loadPostponed();
    })
  );
}

// ---------- transactions ----------

async function loadTransactions() {
  const cat = $("#tx-filter").value;
  const t = await api(`/api/transactions?limit=150${cat ? `&category=${cat}` : ""}`);
  CATEGORY_NAMES = t.categories;
  const options = Object.entries(CATEGORY_NAMES).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("");
  if (!$("#tx-filter").options.length) $("#tx-filter").innerHTML = `<option value="">All categories</option>${options}`;
  $("#tx-body").innerHTML = t.transactions
    .map(
      (x) => `
    <tr class="border-b border-slate-100">
      <td class="p-3 whitespace-nowrap text-slate-500">${x.date}</td>
      <td class="p-3"><div class="max-w-md truncate" title="${esc(x.description)}">${esc(x.description)}</div>
        <div class="text-xs text-slate-400">${x.source === "paypal" ? "PayPal Sandbox" : "Demo bank"}</div></td>
      <td class="p-3 text-right whitespace-nowrap ${x.amount > 0 ? "text-green-700" : ""}">${money(x.amount, 2)}</td>
      <td class="p-3 whitespace-nowrap">
        <select class="tx-cat" data-tx="${esc(x.id)}">${Object.entries(CATEGORY_NAMES)
          .map(([k, v]) => `<option value="${k}" ${k === x.category ? "selected" : ""}>${esc(v)}</option>`)
          .join("")}</select>
        <span class="text-xs ${x.category_source === "user" ? "text-teal-700" : "text-slate-400"}">${x.category_source === "user" ? "you" : "AI"}</span>
      </td>
    </tr>`
    )
    .join("");
  document.querySelectorAll("[data-tx]").forEach((s) =>
    s.addEventListener("change", async () => {
      const r = await api(`/api/transactions/${encodeURIComponent(s.dataset.tx)}/category`, { method: "POST", body: JSON.stringify({ category: s.value }) });
      $("#tx-msg").textContent = `Saved. Also updated ${r.updated_same_merchant} other transaction(s) from this merchant. The AI is retraining with your fix in the background.`;
      await Promise.all([loadTransactions(), loadSummary()]);
    })
  );
}

// ---------- purchase check ----------

function renderVerdict(r, form) {
  const titles = { red: "Better to postpone", yellow: "Think it over", green: "Looks fine" };
  const icons = { red: "🔴", yellow: "🟡", green: "🟢" };
  $("#check-result").innerHTML = `
    <div class="verdict verdict-${r.light}">
      <div class="text-lg font-semibold">${icons[r.light]} ${titles[r.light]}</div>
      <div class="text-sm text-slate-600 mt-1">${esc(r.title)} · ${money(r.price, 2)} · ${esc(r.category_name)}</div>
      <p class="mt-3">${esc(r.reason)}</p>
      ${r.probability_after != null ? `<div class="text-sm text-slate-600 mt-2">Chance of overspending ${esc(r.category_name)} this month: ${pct(r.probability_before)} now → <b>${pct(r.probability_after)}</b> with this purchase.</div>` : ""}
      <div class="flex gap-2 mt-4">
        <button class="btn-primary" id="btn-postpone">Postpone</button>
        <span class="text-xs text-slate-500 self-center">${esc(r.disclaimer)}</span>
      </div>
    </div>`;
  $("#btn-postpone").addEventListener("click", async () => {
    await api("/api/postpone", {
      method: "POST",
      body: JSON.stringify({ title: form.title, price: form.price, url: form.url, category: r.category, probability: r.probability_after }),
    });
    toast("Postponed. FinPilot will remind you next month.");
    await loadPostponed();
  });
}

// ---------- assistant ----------

function addMsg(text, who) {
  const div = document.createElement("div");
  div.className = who === "user" ? "msg-user" : "msg-bot";
  div.textContent = text;
  $("#chat-log").appendChild(div);
  $("#chat-log").scrollTop = $("#chat-log").scrollHeight;
}

async function sendChat(text) {
  addMsg(text, "user");
  try {
    const r = await api("/api/chat", { method: "POST", body: JSON.stringify({ message: text }) });
    addMsg(r.reply, "bot");
    if (r.refresh) await refreshAll();
  } catch (e) {
    addMsg(e.message, "bot");
  }
}

function setupChat() {
  const suggestions = ["How much did I spend on dining?", "Can I buy a $200 jacket?", "How are my goals?", "Where am I losing money?"];
  $("#chat-suggestions").innerHTML = suggestions.map((s) => `<button class="suggestion">${esc(s)}</button>`).join("");
  document.querySelectorAll(".suggestion").forEach((b) => b.addEventListener("click", () => sendChat(b.textContent)));
  $("#chat-toggle").addEventListener("click", () => {
    $("#chat").classList.toggle("hidden");
    if (!$("#chat-log").children.length) addMsg("Hi! Ask me about your spending, your goals, or whether you can afford something.", "bot");
    $("#chat-input").focus();
  });
  $("#chat-close").addEventListener("click", () => $("#chat").classList.add("hidden"));
  $("#chat-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const text = $("#chat-input").value.trim();
    if (!text) return;
    $("#chat-input").value = "";
    sendChat(text);
  });
}

// ---------- wiring ----------

async function refreshAll() {
  const s = await loadStatus();
  const hasData = s.transactions > 0;
  $("#connect").classList.toggle("hidden", hasData);
  ["#dashboard", "#goals", "#postponed", "#transactions", "#check"].forEach((id) => $(id).classList.toggle("hidden", !hasData));
  if (!hasData) return;
  await loadTransactions();
  await Promise.all([loadSummary(), loadPostponed()]);
}

function setup() {
  $("#btn-demo").addEventListener("click", () => importSource("demo", $("#connect-msg")));
  $("#btn-paypal").addEventListener("click", () => importSource("paypal", $("#connect-msg")));
  $("#btn-reload-demo").addEventListener("click", () => importSource("demo"));
  $("#btn-refresh-paypal").addEventListener("click", () => importSource("paypal"));
  $("#tx-filter").addEventListener("change", loadTransactions);
  $("#btn-add-goal").addEventListener("click", () => $("#goal-form").classList.remove("hidden"));
  $("#btn-cancel-goal").addEventListener("click", () => $("#goal-form").classList.add("hidden"));
  $("#goal-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target));
    try {
      await api("/api/goals", { method: "POST", body: JSON.stringify({ name: f.name, target: Number(f.target), saved: Number(f.saved || 0), deadline: f.deadline }) });
      e.target.reset();
      $("#goal-form").classList.add("hidden");
      await loadSummary();
    } catch (err) {
      toast(err.message);
    }
  });
  $("#check-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target));
    const body = { title: f.title, price: Number(f.price), url: f.url };
    try {
      renderVerdict(await api("/api/check-purchase", { method: "POST", body: JSON.stringify(body) }), body);
    } catch (err) {
      toast(err.message);
    }
  });
  setupChat();
  refreshAll().catch((e) => toast(e.message));
}

setup();
