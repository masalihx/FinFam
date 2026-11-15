// FinPilot assistant. Gemini is taught through context (family facts, rules, examples from our intent
// dataset) and gets our ML models as tools. Every number comes from a tool, never from Gemini.
// Without a Gemini key, our own intent model picks the tool and a template answers.
import { CATEGORY_NAMES, isSpending, monthSummary, monthlyFreeCash, planGoal, planGoals, upcomingRecurring } from "./finance.js";
import { addDays, monthIndex, monthStr } from "./dates.js";
import { checkPurchase } from "./verdict.js";
import { generate, textOf } from "./gemini.js";

let SPEC = null;
async function spec(base = "") { SPEC ||= await (await fetch(`${base}data/assistant_spec.json`)).json(); return SPEC; }
const r2 = (x) => Math.round(x * 100) / 100;

// ------------------------------------------------------------------ tools (our code and models)

function names(app) { return Object.fromEntries(app.store.members().map((m) => [m.id, m.name])); }

const TOOLS = {
  get_month_summary(app) {
    const s = monthSummary(app.models, app.store.data.transactions, app.store.members(), app.today, app.store.limits());
    return { days_left: s.days_left, spent_this_month: r2(s.spent_this_month), income_this_month: r2(s.income_this_month),
      kept_per_month: r2(s.free_cash_per_month), categories: s.categories.filter((c) => c.budget).map((c) => ({
        category: c.name, spent: r2(c.spent), usual_or_limit: r2(c.budget), limit_set_by_family: c.limit_set_by_family,
        chance_of_going_over: r2(c.overspend_probability), expected_rest_of_month: r2(c.expected_rest_of_month || 0) })) };
  },
  get_spending(app, { category, month, scope } = {}) {
    const me = app.store.me, mi = /^\d{4}-\d{2}$/.test(month || "") ? monthIndex(`${month}-01`) : monthIndex(app.today);
    let tx = app.store.data.transactions.filter((t) => monthIndex(t.date) === mi && isSpending(t));
    if (scope === "me") tx = tx.filter((t) => t.member_id === me.id);
    if (category) tx = tx.filter((t) => t.category === category);
    const by = (key) => { const o = {}; for (const t of tx) o[key(t)] = r2((o[key(t)] || 0) - t.amount); return o; };
    return { month: monthStr(mi), scope: scope || "family", total: r2(-tx.reduce((a, t) => a + t.amount, 0)), payments: tx.length,
      by_category: by((t) => CATEGORY_NAMES[t.category] || t.category), by_person: by((t) => names(app)[t.member_id] || "?") };
  },
  get_upcoming(app, { days = 30 } = {}) {
    const n = names(app), until = addDays(app.today, days);
    const regular = upcomingRecurring(app.models, app.store.data.transactions, app.today, days).filter((u) => u.amount < 0)
      .map((u) => ({ date: u.date, name: u.name, amount: r2(-u.amount), how_often: u.frequency, who: n[u.member_id] }));
    const plans = app.store.data.plans.filter((p) => p.date >= app.today && p.date <= until).map((p) => ({ date: p.date, name: p.name, amount: p.amount, planned: true, who: n[p.member_id] }));
    const items = [...regular, ...plans].sort((a, b) => (a.date < b.date ? -1 : 1));
    return { days, total: r2(items.reduce((a, i) => a + i.amount, 0)), items };
  },
  get_goals(app) {
    const s = app.store, free = monthlyFreeCash(s.data.transactions, app.today), me = s.me;
    const pick = (g) => ({ name: g.name, target: g.target, saved: g.saved, deadline: g.deadline, needed_per_month: g.needed_per_month,
      gets_per_month: g.allocated_per_month, projected_date: g.projected_date, on_track: g.on_track });
    return { kept_per_month: r2(free), family_goals: planGoals(s.data.goals.filter((g) => g.member_id === null), free, app.today).map(pick),
      my_goals: s.data.goals.filter((g) => g.member_id === me.id).map((g) => pick(planGoal(g, app.today))) };
  },
  async check_purchase(app, { title = "", price, url = "" } = {}) {
    const r = await checkPurchase(app, { title, price, url });
    return { verdict: r.title_text, reasons: r.reasons, category: r.category_name, reasonable_price_for_family: r.reasonable_price ? r2(r.reasonable_price) : null,
      no_room_this_month: r.no_room_this_month, fresh_month_starts: r.next_month_starts,
      chance_of_going_over_before: r.risk_before != null ? r2(r.risk_before) : null, chance_after: r.risk_after != null ? r2(r.risk_after) : null,
      similar_items_cost: r.market ? `$${Math.round(r.market.low)}-${Math.round(r.market.high)} (2023 prices)` : null };
  },
  where_losing_money(app) {
    const tx = app.store.data.transactions, last = monthIndex(app.today) - 1;
    const monthly = (mi, c) => -tx.filter((t) => monthIndex(t.date) === mi && t.category === c && isSpending(t)).reduce((a, t) => a + t.amount, 0);
    const cats = [...new Set(tx.filter(isSpending).map((t) => t.category))];
    const grew = cats.map((c) => {
      const hist = [1, 2, 3, 4, 5, 6].map((k) => monthly(last - k, c)).sort((a, b) => a - b);
      const usual = (hist[2] + hist[3]) / 2, now = monthly(last, c);
      return { category: CATEGORY_NAMES[c] || c, last_month: r2(now), usual: r2(usual), extra: r2(now - usual) };
    }).filter((g) => g.extra > 20).sort((a, b) => b.extra - a.extra).slice(0, 3);
    const income = tx.filter((t) => monthIndex(t.date) === last && t.category === "income" && t.source !== "allowance").reduce((a, t) => a + t.amount, 0);
    const wants = cats.filter((c) => app.store.kindOf(c) === "want").reduce((a, c) => a + monthly(last, c), 0);
    const subs = monthly(last, "subscriptions");
    return { month: monthStr(last), grew_most: grew, wants_share_of_income: income > 0 ? r2(wants / income) : null, subscriptions_per_month: r2(subs), subscriptions_per_year: r2(subs * 12) };
  },
  get_postponed(app) {
    const p = app.store.data.postponed;
    return { waiting: p.filter((i) => i.status === "waiting").map((i) => ({ title: i.title, price: i.price, reminder: i.remind_on })),
      kept_by_not_buying: r2(p.filter((i) => i.status === "dropped").reduce((a, i) => a + i.price, 0)) };
  },
};

// ------------------------------------------------------------------ teaching context

function instruction(app, sp) {
  const s = app.store, me = s.me;
  const nw = Object.entries(s.data.family.needs_wants).map(([c, v]) => `${CATEGORY_NAMES[c] || c}: ${v.kind}${v.limit ? ` (limit $${Math.round(v.limit)}/month)` : ""}`).join("; ") || "not set yet (use the AI's defaults)";
  return sp.instruction.replace("{today}", app.today)
    .replace("{family}", `${s.data.family.name}; ${s.members().map((m) => `${m.name} (${m.role})`).join(", ")}`)
    .replace("{me}", `${me.name}, a ${me.role}`)
    .replace("{needs_wants}", nw)
    .replace("{examples}", sp.examples.map((e) => `  "${e.q}" -> ${e.tool || "no tool"}`).join("\n"))
    .replace("{categories}", Object.keys(CATEGORY_NAMES).join(", "));
}

// ------------------------------------------------------------------ answering

export async function answer(app, message, context = null, history = [], base = "") {
  const sp = await spec(base);
  const text = context?.price ? `${message}\n(The item on the page: "${context.title}", $${context.price}${context.url ? `, ${context.url}` : ""})` : message;
  if (!app.store.data.settings.gemini_key) return offline(app, sp, text, context);
  const contents = [...history.slice(-6), { role: "user", parts: [{ text }] }];
  const used = [];
  for (let step = 0; step < 4; step++) {
    const data = await generate(app.store.data.settings, {
      systemInstruction: { parts: [{ text: instruction(app, sp) }] }, contents,
      tools: [{ functionDeclarations: sp.tools }], generationConfig: { temperature: 0.2 },
    });
    const content = data.candidates?.[0]?.content;
    const calls = (content?.parts || []).filter((p) => p.functionCall);
    if (!calls.length) return { reply: textOf(data) || "Sorry, I could not answer that.", tools: used, by: "gemini" };
    contents.push(content); // keep the model turn as returned (incl. thought signatures)
    const responses = [];
    for (const { functionCall: fc } of calls) {
      used.push(fc.name);
      let result;
      try { result = TOOLS[fc.name] ? await TOOLS[fc.name](app, fc.args || {}) : { error: "unknown tool" }; } catch (e) { result = { error: e.message }; }
      responses.push({ functionResponse: { name: fc.name, response: { result } } });
    }
    contents.push({ role: "user", parts: responses });
  }
  return { reply: "That took too many steps. Try a simpler question.", tools: used, by: "gemini" };
}

// Offline: our intent model picks the tool; a short template answers.
async function offline(app, sp, text, context) {
  const [{ label, p }] = app.models.intent.proba(text);
  const tool = p < 0.35 ? null : sp.intent_tool[label];
  const money = (x) => `$${Math.round(x).toLocaleString("en-US")}`;
  const note = "\n(Offline answer: add a Gemini key in Settings for a smarter assistant.)";
  if (!tool) return { reply: "Ask me about spending, upcoming bills, goals, or whether something is worth buying." + note, tools: [], by: "intent model" };
  const priceMatch = text.match(/\$\s?(\d[\d,]*(?:\.\d+)?)/);
  const args = tool === "check_purchase" ? { title: context?.title || text, price: priceMatch ? Number(priceMatch[1].replace(",", "")) : context?.price, url: context?.url } : {};
  if (tool === "check_purchase" && !args.price) return { reply: "How much does it cost? For example: “Can I buy a jacket for $120?”", tools: [], by: "intent model" };
  const r = await TOOLS[tool](app, args);
  const lines = {
    get_month_summary: () => [`${r.days_left} days left. Spent ${money(r.spent_this_month)} this month.`, ...r.categories.sort((a, b) => b.chance_of_going_over - a.chance_of_going_over).slice(0, 3).map((c) => `• ${c.category}: ${money(c.spent)} of ${money(c.usual_or_limit)}, risk ${Math.round(c.chance_of_going_over * 100)}%`)],
    get_spending: () => [`Spent ${money(r.total)} in ${r.month} (${r.payments} payments).`, ...Object.entries(r.by_category).sort((a, b) => b[1] - a[1]).slice(0, 4).map(([c, v]) => `• ${c}: ${money(v)}`)],
    get_upcoming: () => [`Next ${r.days} days: ${money(r.total)}.`, ...r.items.slice(0, 6).map((i) => `• ${i.date} ${i.name} ${money(i.amount)}`)],
    get_goals: () => [...r.family_goals, ...r.my_goals].map((g) => `• ${g.name}: ${money(g.saved)} of ${money(g.target)}, needs ${money(g.needed_per_month)}/month${g.on_track === undefined ? "" : g.on_track ? " (on track)" : " (behind)"}`),
    check_purchase: () => [`${r.verdict}.`, ...r.reasons.map((x) => `• ${x}`), r.reasonable_price_for_family ? `Reasonable price for you: up to ${money(r.reasonable_price_for_family)}.` : ""],
    where_losing_money: () => [`In ${r.month}, these grew most:`, ...r.grew_most.map((g) => `• ${g.category}: ${money(g.last_month)} vs usual ${money(g.usual)}`), `Subscriptions: ${money(r.subscriptions_per_year)} a year.`],
    get_postponed: () => [`${r.waiting.length} item(s) waiting.`, ...r.waiting.slice(0, 5).map((i) => `• ${i.title} ${money(i.price)}`)],
  }[tool]();
  return { reply: lines.filter(Boolean).join("\n") + note, tools: [tool], by: "intent model" };
}

export { TOOLS };
