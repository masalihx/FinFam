// Money math done by code (ports of backend/finance.py and backend/ml_service.py). Never by Gemini.
import { FamilyState, FORECAST_CATEGORIES, buildSeries, features, mean, median, nextOccurrence, quantile, sum, vector } from "./features.js";
import { addMonths, daysBetween, daysInMonth, dayOf, monthIndex, parse } from "./dates.js";

export const AVG_DAYS_IN_MONTH = 30.44;
export const CATEGORY_NAMES = {
  groceries: "Groceries", dining: "Dining & coffee", shopping: "Shopping", transportation: "Transport",
  entertainment: "Entertainment", personal_care: "Personal care", subscriptions: "Subscriptions", travel: "Travel",
  health: "Health", housing: "Housing", utilities: "Utilities", insurance: "Insurance",
  education_childcare: "Education & childcare", fees: "Bank fees", income: "Income", transfer: "Transfers",
};
export const isSpending = (t) => t.category !== "income" && t.category !== "transfer";
const familyIncome = (t) => t.category === "income" && t.source !== "allowance";

export function yearlyIncome(tx, today) {
  const from = addMonths(today, -12);
  const last = tx.filter((t) => t.date > from && t.category === "income");
  const months = Math.max(1, Math.min(12, new Set(tx.map((t) => monthIndex(t.date))).size));
  return (sum(last.map((t) => t.amount)) * 12) / months;
}

export function familyState(tx, members, today) {
  const teens = members.filter((m) => m.role === "teen").length;
  return new FamilyState(tx, yearlyIncome(tx, today), teens);
}

export function outsideTransfersOut(window, maxDays = 3) {
  const tr = window.filter((t) => t.category === "transfer").sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
  const incoming = tr.filter((t) => t.amount > 0);
  const used = incoming.map(() => false);
  let outside = 0;
  for (const out of tr.filter((t) => t.amount < 0)) {
    const i = incoming.findIndex((inc, k) => !used[k] && Math.abs(inc.amount + out.amount) < 0.01 && Math.abs(daysBetween(inc.date, out.date)) <= maxDays);
    if (i < 0) outside += -out.amount; else used[i] = true;
  }
  return outside;
}

export function monthlyFreeCash(tx, today, months = 6) {
  const cur = monthIndex(today);
  const w = tx.filter((t) => { const m = monthIndex(t.date); return m < cur && m >= cur - months && t.source !== "allowance"; });
  if (!w.length) return 0;
  const income = sum(w.filter(familyIncome).map((t) => t.amount));
  const spent = -sum(w.filter(isSpending).map((t) => t.amount)) + outsideTransfersOut(w);
  return (income - spent) / Math.max(1, new Set(w.map((t) => monthIndex(t.date))).size);
}

// ------------------------------------------------------------------ goals

export function planGoal(g, today) {
  const monthsLeft = Math.max(0, daysBetween(today, g.deadline) / AVG_DAYS_IN_MONTH);
  const remaining = Math.max(0, g.target - g.saved);
  const needed = monthsLeft > 0 ? remaining / monthsLeft : remaining;
  return { ...g, months_left: Math.round(monthsLeft * 10) / 10, needed_per_month: Math.round(needed * 100) / 100,
    progress: g.target ? g.saved / g.target : 0 };
}

export function planGoals(goals, freeCash, today, maxMonths = 600) {
  const plans = [...goals].sort((a, b) => (a.deadline < b.deadline ? -1 : 1)).map((g) => planGoal(g, today));
  const remaining = plans.map((p) => Math.max(0, p.target - p.saved));
  const done = remaining.map((r) => (r === 0 ? 0 : null));
  let first = plans.map(() => 0);
  for (let m = 1; m <= maxMonths; m++) {
    let available = Math.max(0, freeCash);
    const given = plans.map(() => 0);
    plans.forEach((p, i) => { if (done[i] === null) { const g = Math.min(p.needed_per_month, remaining[i], available); remaining[i] -= g; available -= g; given[i] += g; } });
    plans.forEach((p, i) => { if (done[i] === null && available > 0) { const g = Math.min(remaining[i], available); remaining[i] -= g; available -= g; given[i] += g; } });
    if (m === 1) first = [...given];
    plans.forEach((p, i) => { if (done[i] === null && remaining[i] <= 0.005) done[i] = m - 1 + Math.min(1, given[i] / Math.max(p.needed_per_month, given[i], 1e-9)); });
    if (done.every((d) => d !== null) || freeCash <= 0) break;
  }
  return plans.map((p, i) => {
    let projected = "not reached at the current pace", onTrack = false;
    if (done[i] !== null) {
      const ms = Date.UTC(...(([y, mo, d]) => [y, mo - 1, d])(today.split("-").map(Number))) + done[i] * AVG_DAYS_IN_MONTH * 86400000;
      projected = new Date(ms).toISOString().slice(0, 10);
      onTrack = projected <= p.deadline;
    }
    return { ...p, projected_date: projected, on_track: onTrack, allocated_per_month: Math.round(first[i] * 100) / 100 };
  });
}

// ------------------------------------------------------------------ month summary and risk

export function riskRow(models, state, category, today, extra = 0, limit = null) {
  const row = features(state, category, today, extra, limit);
  if (!row) return null;
  const spec = models.overspendSpec;
  return { row, p: models.overspend.proba(vector(row, spec.features)) };
}

export function lightOf(models, p) {
  if (p == null) return null;
  return p >= models.overspendSpec.red ? "red" : p >= models.overspendSpec.threshold ? "yellow" : "green";
}

export function monthSummary(models, tx, members, today, limits) {
  const state = familyState(tx, members, today);
  const cur = monthIndex(today);
  const month = tx.filter((t) => monthIndex(t.date) === cur);
  const spentBy = {};
  for (const t of month.filter(isSpending)) spentBy[t.category] = (spentBy[t.category] || 0) - t.amount;
  const categories = FORECAST_CATEGORIES.map((c) => {
    const r = riskRow(models, state, c, today, 0, limits[c] ?? null);
    return { category: c, name: CATEGORY_NAMES[c], spent: spentBy[c] || 0, budget: r ? r.row.budget : null,
      limit_set_by_family: limits[c] != null, expected_rest_of_month: r ? r.row.hist_after_day_ratio * r.row.budget : null,
      overspend_probability: r ? r.p : null, light: r ? lightOf(models, r.p) : null };
  });
  const other = Object.fromEntries(Object.entries(spentBy).filter(([c, v]) => !FORECAST_CATEGORIES.includes(c) && v > 0));
  const trend = [];
  for (let m = cur - 5; m <= cur; m++) {
    const row = { month: m };
    for (const t of tx) if (monthIndex(t.date) === m && isSpending(t)) row[t.category] = (row[t.category] || 0) - t.amount;
    trend.push(row);
  }
  const byMember = members.map((mb) => ({ ...mb, spent: -sum(month.filter((t) => isSpending(t) && t.member_id === mb.id).map((t) => t.amount)) }));
  const { y, m } = parse(today);
  return { today, days_left: daysInMonth(y, m) - dayOf(today), income_this_month: sum(month.filter(familyIncome).map((t) => t.amount)),
    spent_this_month: -sum(month.filter(isSpending).map((t) => t.amount)), free_cash_per_month: monthlyFreeCash(tx, today),
    categories, other_spending: other, trend, by_member: byMember, state };
}

export function usualP90(tx, category, today) {
  const from = addMonths(today, -12);
  const h = tx.filter((t) => t.category === category && t.amount < -5 && t.date < today && t.date >= from).map((t) => -t.amount);
  return h.length >= 5 ? quantile(h, 0.9) : null;
}

// ------------------------------------------------------------------ recurring payments

const BANK_WORDS = new Set(["ach", "electronic", "debit", "credit", "pay", "org", "card", "purchase", "recurring", "web", "ppd",
  "online", "payment", "des", "indn", "co", "pmt", "auto", "ca", "wa", "ny", "tx", "fl", "il", "ma"]);
const title = (s) => s.replace(/\b\w/g, (c) => c.toUpperCase());

export function prettyName(key, merchant) {
  if (merchant && merchant.trim() && !["zelle", "venmo", "paypal"].includes(merchant.trim().toLowerCase())) return merchant.trim().slice(0, 40);
  const m = key.match(/name:\s*([a-z]+(?:\s[a-z]+)?)/);
  if (key.includes("zelle") && m) return `Zelle to ${title(m[1])}`;
  const words = key.split(/[\s*]+/).filter((w) => w && !BANK_WORDS.has(w) && !w.includes(":") && w.length > 1);
  return title(words.slice(0, 3).join(" ")) || title(key).slice(0, 40);
}

export function upcomingRecurring(models, tx, today, days = 30) {
  const series = buildSeries(tx.filter((t) => t.date <= today), 3);
  const spec = models.recurringSpec, out = [];
  for (const s of series) {
    const p = models.recurring.proba(vector(s.feats, spec.features));
    if (p < 0.5) continue;
    if (daysBetween(s.lastDate, today) > Math.max(45, 2.5 * s.feats.gap_median)) continue;
    const next = nextOccurrence(s.lastDate, s.feats.gap_median, today);
    if (daysBetween(today, next) > days) continue;
    const gm = s.feats.gap_median;
    const freq = gm <= 9 ? "weekly" : gm <= 18 ? "every 2 weeks" : gm <= 40 ? "monthly" : gm > 300 ? "yearly" : `every ${Math.round(gm)} days`;
    const merchant = s.members.map((t) => t.merchant).filter(Boolean).pop();
    out.push({ date: next, name: prettyName(s.key, merchant), amount: s.medianAmount, frequency: freq, confidence: p,
      category: s.example.category, member_id: s.example.member_id, key: s.key });
  }
  return out.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
}

// ------------------------------------------------------------------ needs and wants (start screen)

export function setupSuggestions(models, tx, today, recurringByCategory) {
  const cur = monthIndex(today);
  const w = tx.filter((t) => { const m = monthIndex(t.date); return m < cur && m >= cur - 6 && isSpending(t); });
  if (!w.length) return [];
  const months = [...new Set(w.map((t) => monthIndex(t.date)))];
  const cats = [...new Set(w.map((t) => t.category))];
  const out = [];
  for (const c of cats) {
    const monthly = months.map((m) => -sum(w.filter((t) => t.category === c && monthIndex(t.date) === m).map((t) => t.amount)));
    const med = median(monthly);
    if (med < 5) continue;
    const regular = recurringByCategory[c] || [];
    let kind = models.needs.has(c) ? "need" : models.wants.has(c) ? "want" : regular.length ? "need" : "want";
    const why = regular.length ? "Regular payments: " + [...new Set(regular)].slice(0, 3).join(", ")
      : kind === "need" ? "Bills and essentials" : "Day-to-day choices you can adjust";
    out.push({ category: c, name: CATEGORY_NAMES[c] || c, kind, usual_per_month: med, suggested_limit: kind === "want" ? med : null, why });
  }
  return out.sort((a, b) => (a.kind !== b.kind ? (a.kind === "need" ? -1 : 1) : b.usual_per_month - a.usual_per_month));
}

export { mean, median };
