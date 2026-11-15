// Live features for the ML models: exact ports of ml/live_features.py, ml/overspend_features.py
// and ml/recurring.py. Transactions: {date, amount, description, category, member_id, merchant, source}.
import { normalize } from "./ml.js";
import { addDays, addMonths, daysBetween, daysInMonth, dayOf, monthIndex, parse } from "./dates.js";

export const FORECAST_CATEGORIES = ["groceries", "dining", "shopping", "transportation", "entertainment",
  "personal_care", "subscriptions", "travel", "health"];
const HISTORY_MONTHS = 6, MIN_HISTORY = 3, OVER_MARGIN = 0.10;

// ------------------------------------------------------------------ statistics (numpy semantics)
export const sum = (a) => a.reduce((s, v) => s + v, 0);
export const mean = (a) => sum(a) / a.length;
export function median(a) {
  const s = [...a].sort((x, y) => x - y), n = s.length;
  return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2;
}
export function std(a, ddof = 0) {
  const m = mean(a);
  return Math.sqrt(sum(a.map((v) => (v - m) ** 2)) / (a.length - ddof));
}
export function quantile(a, q) { // numpy linear interpolation
  const s = [...a].sort((x, y) => x - y);
  const pos = (s.length - 1) * q, lo = Math.floor(pos), hi = Math.ceil(pos);
  return s[lo] + (s[hi] - s[lo]) * (pos - lo);
}
export function roundHalfEven(x) {
  const r = Math.round(x);
  return Math.abs(x % 1) === 0.5 ? (r % 2 === 0 ? r : r - 1) : r;
}

// ------------------------------------------------------------------ overspend features

export class FamilyState {
  constructor(tx, householdIncome, children) {
    this.householdIncome = householdIncome;
    this.children = children;
    this.firstMonth = Math.min(...tx.map((t) => monthIndex(t.date)));
    this.spend = new Map();   // `${cat}|${month}` -> Map(day -> {spend, n})
    this.income = new Map();  // month -> Map(day -> amount)
    for (const t of tx) {
      const mi = monthIndex(t.date), day = dayOf(t.date);
      if (FORECAST_CATEGORIES.includes(t.category) && !t.is_fraud) {
        const key = `${t.category}|${mi}`;
        if (!this.spend.has(key)) this.spend.set(key, new Map());
        const m = this.spend.get(key), cell = m.get(day) || { spend: 0, n: 0 };
        cell.spend += -t.amount; cell.n += 1; m.set(day, cell);
      } else if (t.category === "income") {
        if (!this.income.has(mi)) this.income.set(mi, new Map());
        const m = this.income.get(mi);
        m.set(day, (m.get(day) || 0) + t.amount);
      }
    }
  }
  monthSpend(cat, mi, uptoDay = 99) {
    let s = 0, n = 0;
    for (const [d, c] of this.spend.get(`${cat}|${mi}`) || []) if (d <= uptoDay) { s += c.spend; n += c.n; }
    return { s, n };
  }
  monthIncome(mi, uptoDay = 99) {
    let s = 0;
    for (const [d, v] of this.income.get(mi) || []) if (d <= uptoDay) s += v;
    return s;
  }
  // Raw feature row for `category` on day `asOf`, with `extra` added to spending so far; null without history.
  raw(category, asOf, extra = 0) {
    const mi = monthIndex(asOf), day = dayOf(asOf);
    const start = Math.max(this.firstMonth, mi - HISTORY_MONTHS);
    const prev = [];
    for (let m = start; m <= mi - 1; m++) prev.push(m);
    if (prev.length < MIN_HISTORY) return null;
    const totals = [], toDay = [], nTotals = [], incomes = [];
    for (const m of prev) {
      const all = this.monthSpend(category, m), upto = this.monthSpend(category, m, day);
      totals.push(all.s); toDay.push(upto.s); nTotals.push(all.n); incomes.push(this.monthIncome(m));
    }
    const budget = median(totals);
    if (budget <= 1.0) return null;
    const cur = this.monthSpend(category, mi, day);
    const { y, m } = parse(asOf);
    return {
      label: category, month: mi, month_of_year: m, day, days_in_month: daysInMonth(y, m),
      spent_to_date: cur.s + extra, n_tx_to_date: cur.n + (extra > 0 ? 1 : 0), budget,
      hist_mean: mean(totals), hist_std: totals.length > 1 ? std(totals, 1) : 0, hist_max: Math.max(...totals),
      hist_n_tx: mean(nTotals), hist_to_day: mean(toDay),
      hist_over_share: mean(totals.map((t) => (t > budget * (1 + OVER_MARGIN) ? 1 : 0))),
      income_to_date: this.monthIncome(mi, day), hist_income: mean(incomes),
      household_income: this.householdIncome, children: this.children,
    };
  }
}

// Port of add_features(): ratios computed from a raw row (also after a budget override).
export function addFeatures(r) {
  const b = Math.max(r.budget, 1.0);
  return {
    ...r,
    days_left: r.days_in_month - r.day,
    spent_ratio: r.spent_to_date / b,
    proportion_ratio: (r.spent_to_date * r.days_in_month) / r.day / b,
    pace_ratio: r.spent_to_date / Math.max(r.hist_to_day, 1.0),
    hist_after_day_ratio: Math.max(r.hist_mean - r.hist_to_day, 0) / b,
    hist_mean_ratio: r.hist_mean / b,
    hist_std_ratio: (r.hist_std || 0) / b,
    hist_max_ratio: r.hist_max / b,
    n_tx_ratio: r.n_tx_to_date / Math.max(r.hist_n_tx, 1.0),
    income_to_date_ratio: r.income_to_date / Math.max(r.hist_income, 1.0),
    category_code: FORECAST_CATEGORIES.indexOf(r.label),
  };
}

export function features(state, category, asOf, extra = 0, budgetOverride = null) {
  const r = state.raw(category, asOf, extra);
  if (!r) return null;
  if (budgetOverride != null) r.budget = Number(budgetOverride);
  return addFeatures(r);
}

export const vector = (row, names) => names.map((f) => row[f]);

// ------------------------------------------------------------------ recurring payments

export function merchantKey(description) {
  const toks = normalize(description).split(" ").filter((t) => t && !t.includes("0") && !/^\W+$/.test(t)
    && t !== "[debit]" && t !== "[credit]");
  return toks.slice(0, 6).join(" ");
}

function seriesFeatures(g, monthsObserved) {
  const dates = g.map((t) => t.date);
  const gaps = dates.slice(1).map((d, i) => daysBetween(dates[i], d));
  const amounts = g.map((t) => Math.abs(t.amount));
  const gm = gaps.length ? median(gaps) : 0;
  const nMonths = new Set(dates.map(monthIndex)).size;
  const near = (target, tol) => (gaps.length ? mean(gaps.map((x) => (Math.abs(x - target) <= tol ? 1 : 0))) : 0);
  const med = median(amounts);
  return {
    n: g.length, n_months: nMonths, month_coverage: nMonths / Math.max(1, monthsObserved), gap_median: gm,
    gap_cv: gaps.length > 1 && gm > 0 ? std(gaps) / gm : 3.0,
    gap_near_month: near(30.4, 4), gap_near_week: near(7, 1), gap_near_2weeks: near(14, 2),
    amount_log: Math.log1p(med), amount_cv: med > 0 ? std(amounts) / med : 0,
    amount_same_share: mean(amounts.map((a) => (Math.abs(a - med) <= 0.01 * Math.max(med, 1) ? 1 : 0))),
    day_of_month_std: std(dates.map(dayOf)), is_inflow: g[0].amount > 0 ? 1 : 0,
    span_days: daysBetween(dates[0], dates[dates.length - 1]),
  };
}

export function buildSeries(tx, minN = 2) {
  const monthsObserved = new Set(tx.map((t) => monthIndex(t.date))).size;
  const groups = new Map();
  for (const t of tx) {
    const key = merchantKey(t.description);
    if (!key) continue;
    const k = `${key}|${t.amount > 0}`;
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(t);
  }
  const out = [];
  for (const [k, g] of groups) {
    if (g.length < minN) continue;
    g.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
    out.push({ key: k.slice(0, k.lastIndexOf("|")), feats: seriesFeatures(g, monthsObserved), lastDate: g[g.length - 1].date,
      medianAmount: median(g.slice(-3).map((t) => t.amount)), example: g[g.length - 1], members: g });
  }
  return out;
}

export function nextOccurrence(lastDate, gapMedian, after) {
  let d = lastDate;
  if (gapMedian >= 26 && gapMedian <= 35) { // monthly: same day next month (clamped, like pandas)
    while (d <= after) d = addMonths(d, 1);
    return d;
  }
  const step = Math.max(1, roundHalfEven(gapMedian));
  while (d <= after) d = addDays(d, step);
  return d;
}
