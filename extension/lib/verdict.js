// Product verdict: Buy / Think about it / Not worth it (port of ml/verdict.py).
// Inputs are ML outputs: overspend risk, market price from our database, the family's usual prices, goals.
import { FORECAST_CATEGORIES } from "./features.js";
import { CATEGORY_NAMES, monthlyFreeCash, planGoals, riskRow, familyState, usualP90, AVG_DAYS_IN_MONTH } from "./finance.js";
import { daysInMonth, dayOf, monthIndex, firstOfMonth, parse } from "./dates.js";

const RED_RISK = 0.75, MIN_RISK_JUMP = 0.05, MARKET_TOLERANCE = 0.10, MIN_GOAL_PRICE = 20;
// Show a market price only if the listed price is within 3x of the similar items' range (ml/train_price_knn.py:
// on unseen stores this keeps 96% of items at 32.7% median error; the hidden 4% had 88.6%, mostly accessories with the same name).
const MARKET_GATE = 3;
const niceDate = (s) => new Date(`${s}T00:00:00`).toLocaleDateString("en-US", { month: "long", day: "numeric" });
const money = (x) => "$" + Math.round(x).toLocaleString("en-US");
const pct = (p) => `${Math.round(p * 100)}%`;

// ------------------------------------------------------------------ product category

const SITE_CATEGORIES = {
  "amazon.": "shopping", "walmart.": "shopping", "target.": "shopping", "ebay.": "shopping", "etsy.": "shopping",
  "bestbuy.": "shopping", "temu.": "shopping", "shein.": "shopping", "aliexpress.": "shopping", "nike.": "shopping",
  "doordash.": "dining", "ubereats.": "dining", "grubhub.": "dining", "instacart.": "groceries", "wholefoodsmarket.": "groceries",
  "ticketmaster.": "entertainment", "stubhub.": "entertainment", "steampowered.": "entertainment", "fandango.": "entertainment",
  "livenation.": "entertainment", "booking.": "travel", "expedia.": "travel", "airbnb.": "travel", "delta.": "travel",
  "united.": "travel", "sephora.": "personal_care", "ulta.": "personal_care", "cvs.": "health", "walgreens.": "health",
};
const TITLE_KEYWORDS = {
  education_childcare: ["textbook", "school supplies", "backpack for school", "calculator", "notebook", "pencil", "tuition", "course"],
  health: ["vitamin", "supplement", "medicine", "first aid", "thermometer", "allergy", "pain relief"],
  groceries: ["grocery", "snack", "coffee beans", "cereal", "pantry", "beverage", "organic food"],
  entertainment: ["ticket", "concert", "festival", "game pass", "video game", "playstation", "xbox", "nintendo", "movie"],
  travel: ["flight", "hotel", "airfare", "vacation package"],
  personal_care: ["shampoo", "skincare", "makeup", "cosmetic", "perfume", "razor"],
  subscriptions: ["subscription", "membership", "monthly plan"],
  dining: ["restaurant", "meal delivery", "pizza", "burger"],
};
const MARKET_CATEGORIES = new Set(["shopping", "personal_care", "health", "education_childcare", "groceries"]);

export function categoryForProduct(title, url) {
  let host = "";
  try { host = new URL(url).hostname.toLowerCase(); } catch { /* no url */ }
  const low = (title || "").toLowerCase();
  const byWords = (cats) => Object.entries(TITLE_KEYWORDS).find(([c, ws]) => cats.includes(c) && ws.some((w) => low.includes(w)))?.[0];
  const site = Object.entries(SITE_CATEGORIES).find(([k]) => host.includes(k))?.[1];
  if (site) return byWords(["education_childcare", "health", "entertainment"]) || site;
  return byWords(Object.keys(TITLE_KEYWORDS)) || "shopping";
}

// ------------------------------------------------------------------ decision rules

export function decide(s) {
  const reasons = [], checks = {};
  const overMarket = s.marketHigh != null && s.price > s.marketHigh * (1 + MARKET_TOLERANCE);
  const nearTop = s.marketLow != null && !overMarket && s.price > (s.marketLow + s.marketHigh) / 2;
  checks.above_market = overMarket;
  if (overMarket) reasons.push(`Similar items cost ${money(s.marketLow)}–${money(s.marketHigh)}; this is ${pct(s.price / s.marketHigh - 1)} above that range.`);
  if (s.isNeed) {
    checks.need = true;
    if (!overMarket) reasons.push(`${s.categoryName} counts as a need, and the price looks normal.`);
    return { decision: overMarket ? "not_worth_it" : nearTop ? "think" : "buy", reasons, checks };
  }
  const jump = s.riskAfter != null && s.riskBefore != null ? s.riskAfter - s.riskBefore : 0;
  const highRisk = s.riskAfter != null && s.riskAfter >= RED_RISK && jump >= MIN_RISK_JUMP;
  const someRisk = s.riskAfter != null && s.riskAfter >= s.warnThreshold;
  checks.high_risk = highRisk;
  if (s.riskAfter != null && (highRisk || someRisk)) {
    reasons.push(jump < MIN_RISK_JUMP
      ? `Your ${s.categoryName} spending is already likely to go over this month (${pct(s.riskAfter)}); this small purchase adds little, but every bit counts.`
      : `Chance of going over your usual ${s.categoryName} spending this month: ${pct(s.riskBefore)} → ${pct(s.riskAfter)} with this purchase.`);
  }
  const aboveUsual = s.usualP90 != null && s.price > s.usualP90;
  checks.above_usual = aboveUsual;
  if (aboveUsual) reasons.push(`More than your family usually pays for ${s.categoryName}: 9 out of 10 of your purchases there are under ${money(s.usualP90)}.`);
  const hurtsGoal = s.goalBehind && s.price >= MIN_GOAL_PRICE;
  checks.hurts_behind_goal = hurtsGoal;
  if (hurtsGoal) reasons.push(`Your goal “${s.goalName}” is already behind; this pushes it back${s.goalDelayDays ? ` by about ${s.goalDelayDays} days` : ""}.`);
  if (overMarket || highRisk || aboveUsual || hurtsGoal) return { decision: "not_worth_it", reasons, checks };
  if (someRisk || nearTop) {
    if (nearTop && !someRisk) reasons.push(`The price is in the upper half of what similar items cost (${money(s.marketLow)}–${money(s.marketHigh)}).`);
    return { decision: "think", reasons, checks };
  }
  if (!reasons.length) reasons.push("Fits your budget and your usual prices.");
  return { decision: "buy", reasons, checks };
}

export function reasonablePrice(riskAt, threshold, upper, tol = 1) {
  if (riskAt(1) >= threshold) return null;
  let lo = 1, hi = Math.max(upper, 2);
  if (riskAt(hi) < threshold) return hi;
  while (hi - lo > tol) { const mid = (lo + hi) / 2; if (riskAt(mid) < threshold) lo = mid; else hi = mid; }
  return lo;
}

// ------------------------------------------------------------------ full check

export function checkPurchase(app, { title = "", price, url = "", category = null }) {
  const s = app.store, models = app.models, today = app.today, tx = s.data.transactions;
  if (!tx.length) throw new Error("No money data yet. Add your expenses and income first.");
  price = Number(price);
  if (!(price > 0)) throw new Error("Enter a price above $0.");
  const cat = CATEGORY_NAMES[category] ? category : categoryForProduct(title, url);
  const kind = s.kindOf(cat), isNeed = kind === "need", name = CATEGORY_NAMES[cat] || cat;
  let market = title.trim() && MARKET_CATEGORIES.has(cat) && app.market ? app.market.lookup(title) : null, marketUnclear = null;
  if (market && (price < market.low / MARKET_GATE || price > market.high * MARKET_GATE)) { marketUnclear = market; market = null; }

  const state = familyState(tx, s.data.family.children, today);
  const forecastable = FORECAST_CATEGORIES.includes(cat);
  const before = forecastable ? riskRow(models, state, cat, today, 0) : null;
  const after = forecastable ? riskRow(models, state, cat, today, price) : null;
  const threshold = models.overspendSpec.threshold;

  const free = monthlyFreeCash(tx, today);
  const goal = planGoals(s.data.goals, free, today).find((g) => !g.on_track) || null;
  const delay = goal && free > 0 ? Math.round(price / (free / AVG_DAYS_IN_MONTH)) : null;

  const v = decide({ price, categoryName: name, isNeed, riskBefore: before?.p ?? null, riskAfter: after?.p ?? null,
    warnThreshold: threshold, usualP90: usualP90(tx, cat, today), marketLow: market?.low ?? null, marketHigh: market?.high ?? null,
    goalName: goal?.name, goalBehind: !!goal && !isNeed, goalDelayDays: delay });

  let reasonable = null;
  if (before && !isNeed) reasonable = reasonablePrice((x) => riskRow(models, state, cat, today, x).p, threshold, Math.max(price * 3, 50));
  const { y, m } = parse(today);
  const r = {
    ...v, title_text: TITLES[v.decision],
    category: cat, category_name: name, kind, risk_before: before?.p ?? null, risk_after: after?.p ?? null,
    spent_this_month: before?.row.spent_to_date ?? null, budget: before?.row.budget ?? null,
    left_this_month: before ? before.row.budget - before.row.spent_to_date : null, days_left: daysInMonth(y, m) - dayOf(today),
    market, market_unclear: marketUnclear && { low: marketUnclear.low, high: marketUnclear.high }, reasonable_price: reasonable, no_room_this_month: !!before && !isNeed && reasonable === null,
    next_month_starts: firstOfMonth(monthIndex(today) + 1), goal: goal?.name || null, goal_delay_days: delay, free_cash: free, title, price, url,
  };
  return { ...r, explain: explainVerdict(r) };
}

// ------------------------------------------------------------------ short explanation (same text in the panel and on the page)

export const TITLES = { buy: "Worth it", think: "Think about it", not_worth_it: "Not worth it" };

export function explainVerdict(r) {
  let family;
  if (r.budget != null) {
    const left = r.left_this_month, days = `${r.days_left} day${r.days_left === 1 ? "" : "s"} to go`;
    family = left > 0
      ? `${r.category_name}: ${money(left)} left of your usual ${money(r.budget)} this month, ${days}.` +
        (r.price > left ? ` This would put you ${money(r.price - left)} over.` : ` After this: ${money(left - r.price)}.`)
      : `${r.category_name}: already ${money(-left)} over your usual ${money(r.budget)} this month, ${days}.`;
  } else {
    family = r.free_cash > 0 ? `Your family keeps about ${money(r.free_cash)} a month after all spending.`
      : "Your family currently spends about everything it earns.";
  }
  const why = r.reasons.find((x) => !x.startsWith("Similar items cost") && !x.startsWith("The price is in the upper half")) || null;
  let market = null;
  if (r.market) {
    const diff = r.price / r.market.median - 1;
    const vs = Math.abs(diff) < 0.05 ? "about the average" : `${pct(Math.abs(diff))} ${diff > 0 ? "above" : "below"} the average`;
    market = { average: r.market.median, low: r.market.low, high: r.market.high, count: r.market.count, diff,
      text: `Average market price: ${money(r.market.median)} (most similar items ${money(r.market.low)}–${money(r.market.high)}). This price is ${vs}.` };
  } else if (r.market_unclear) {
    market = { average: null, text: `No close match in our price database: items with similar names cost ${money(r.market_unclear.low)}–${money(r.market_unclear.high)} (often accessories or other versions).` };
  }
  const fair = r.decision === "buy" ? null : r.reasonable_price ? `A price that fits your budget now: up to ${money(r.reasonable_price)}.`
    : r.no_room_this_month ? `${r.category_name} is already likely to go over this month, so no extra price fits right now. A fresh month starts ${niceDate(r.next_month_starts)}.` : null;
  return { family, why, market, fair };
}
