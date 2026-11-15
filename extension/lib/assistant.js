// FinPilot advisor, fully built in (no external AI). Our intent model (TF-IDF + logistic regression)
// decides what the question is about; our other models and code compute every number.
// If the model is unsure, the answer also offers the next likely topics as one-tap buttons.
import { CATEGORY_NAMES, isSpending, monthSummary, monthlyFreeCash, planGoals, upcomingRecurring } from "./finance.js";
import { addDays, monthIndex, monthStr } from "./dates.js";
import { checkPurchase } from "./verdict.js";

export const TOPICS = {
  spending: "What did we spend?", budget_left: "What's left this month?", upcoming: "Upcoming bills",
  goals: "Our goals", where_losing: "Where are we losing money?", postponed: "Postponed purchases",
  can_afford: "Is it worth it?", help: "What can you do?",
};
const money = (x) => `$${Math.round(x).toLocaleString("en-US")}`;
const pct = (p) => `${Math.round(p * 100)}%`;
const CATEGORY_WORDS = {
  dining: ["dining", "restaurant", "eating out", "eat out", "coffee", "takeout", "delivery", "lunch", "dinner"],
  groceries: ["grocer", "supermarket", "food"], shopping: ["shopping", "clothes", "amazon", "online"],
  transportation: ["transport", "gas", "fuel", "uber", "lyft", "taxi"], entertainment: ["entertainment", "movie", "games", "concert", "ticket"],
  subscriptions: ["subscription", "netflix", "spotify", "streaming"], travel: ["travel", "vacation", "flight", "hotel"],
  health: ["health", "pharmacy", "doctor", "medicine"], personal_care: ["haircut", "salon", "gym", "beauty"],
  utilities: ["bills", "utilities", "electric", "internet", "phone"], housing: ["rent", "mortgage"],
};
const findCategory = (text) => Object.entries(CATEGORY_WORDS).find(([, ws]) => ws.some((w) => text.toLowerCase().includes(w)))?.[0];
const MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"];
function findMonth(text, today) {
  const low = text.toLowerCase(), cur = monthIndex(today);
  if (low.includes("last month")) return cur - 1;
  const i = MONTHS.findIndex((m) => (m === "may" ? /\bin may\b/ : new RegExp(`\\b(${m}|${m.slice(0, 3)})\\b`)).test(low));
  if (i < 0) return cur;
  const y = Number(today.slice(0, 4)), mi = y * 12 + i;
  return mi <= cur ? mi : mi - 12;
}

// ------------------------------------------------------------------ answers per topic

const ANSWERS = {
  spending(app, text) {
    const mi = findMonth(text, app.today), cat = findCategory(text);
    const tx = app.store.data.transactions.filter((t) => monthIndex(t.date) === mi && isSpending(t) && (!cat || t.category === cat));
    const total = -tx.reduce((a, t) => a + t.amount, 0), label = mi === monthIndex(app.today) ? "this month" : `in ${monthStr(mi)}`;
    if (cat) return `You spent ${money(total)} on ${CATEGORY_NAMES[cat]} ${label} (${tx.length} payments).`;
    const by = {};
    for (const t of tx) by[t.category] = (by[t.category] || 0) - t.amount;
    const top = Object.entries(by).sort((a, b) => b[1] - a[1]).slice(0, 4).map(([c, v]) => `• ${CATEGORY_NAMES[c] || c}: ${money(v)}`);
    return [`You spent ${money(total)} ${label}. Biggest:`, ...top].join("\n");
  },
  budget_left(app, text) {
    const s = monthSummary(app.models, app.store.data.transactions, app.store.data.family.children, app.today);
    const cat = findCategory(text);
    const rows = s.categories.filter((c) => c.budget && (!cat || c.category === cat))
      .sort((a, b) => (b.overspend_probability ?? 0) - (a.overspend_probability ?? 0)).slice(0, cat ? 1 : 4);
    if (!rows.length) return "Not enough history yet to know your usual spending.";
    return [`${s.days_left} days left this month.`, ...rows.map((c) => {
      const left = c.budget - c.spent;
      return `• ${c.name}: ${left >= 0 ? `${money(left)} left` : `${money(-left)} over`} of the usual ${money(c.budget)} — ${pct(c.overspend_probability)} chance to go over`;
    })].join("\n");
  },
  upcoming(app) {
    const until = addDays(app.today, 30);
    const items = [...upcomingRecurring(app.models, app.store.data.transactions, app.today, 30).filter((u) => u.amount < 0)
      .map((u) => ({ date: u.date, name: u.name, amount: -u.amount })),
      ...app.store.data.plans.filter((p) => p.date >= app.today && p.date <= until).map((p) => ({ date: p.date, name: p.name, amount: p.amount }))]
      .sort((a, b) => (a.date < b.date ? -1 : 1));
    if (!items.length) return "No regular bills or plans found for the next 30 days.";
    return [`Next 30 days: ${money(items.reduce((a, i) => a + i.amount, 0))} in ${items.length} payments.`,
      ...items.slice(0, 6).map((i) => `• ${i.date.slice(5)} ${i.name} ${money(i.amount)}`)].join("\n");
  },
  goals(app) {
    const free = monthlyFreeCash(app.store.data.transactions, app.today);
    const plans = planGoals(app.store.data.goals, free, app.today);
    if (!plans.length) return `No goals yet. The family keeps about ${money(free)} a month.`;
    return [`The family keeps about ${money(free)} a month.`, ...plans.map((g) =>
      `• ${g.name}: ${money(g.saved)} of ${money(g.target)}, needs ${money(g.needed_per_month)}/month — ${g.on_track ? "on track" : `behind (reached ${g.projected_date})`}`)].join("\n");
  },
  where_losing(app) {
    const tx = app.store.data.transactions, last = monthIndex(app.today) - 1;
    const monthly = (mi, c) => -tx.filter((t) => monthIndex(t.date) === mi && t.category === c && isSpending(t)).reduce((a, t) => a + t.amount, 0);
    const grew = [...new Set(tx.filter(isSpending).map((t) => t.category))].map((c) => {
      const hist = [1, 2, 3, 4, 5, 6].map((k) => monthly(last - k, c)).sort((a, b) => a - b);
      return { c, now: monthly(last, c), usual: (hist[2] + hist[3]) / 2 };
    }).filter((g) => g.now - g.usual > 20).sort((a, b) => b.now - b.usual - (a.now - a.usual)).slice(0, 3);
    const subs = monthly(last, "subscriptions");
    return [`In ${monthStr(last)} these grew most compared with a usual month:`,
      ...(grew.length ? grew.map((g) => `• ${CATEGORY_NAMES[g.c] || g.c}: ${money(g.now)} vs usual ${money(g.usual)}`) : ["• nothing unusual"]),
      subs > 0 ? `Subscriptions cost ${money(subs * 12)} a year — check which ones you still use.` : ""].filter(Boolean).join("\n");
  },
  postponed(app) {
    const p = app.store.data.postponed, waiting = p.filter((i) => i.status === "waiting");
    if (!waiting.length) return "Nothing postponed yet. When FinPilot says “Not worth it”, press Postpone.";
    return [`${waiting.length} item(s) waiting, ${money(waiting.reduce((a, i) => a + i.price, 0))} not spent yet:`,
      ...waiting.slice(0, 5).map((i) => `• ${i.title} ${money(i.price)} (reminder ${i.remind_on})`)].join("\n");
  },
  can_afford(app, text, context) {
    const m = text.match(/\$\s?(\d[\d,]*(?:\.\d+)?)|(\d[\d,]*(?:\.\d+)?)\s?(?:dollars|bucks|usd)/i);
    const price = m ? Number((m[1] || m[2]).replace(/,/g, "")) : context?.price;
    if (!price) return "Tell me the price, for example: “Can I buy sneakers for $90?”";
    const title = context?.title || text.replace(/can i|should i|buy|get|afford|for|\$\s?[\d.,]+|\?/gi, " ").replace(/\s+/g, " ").trim();
    const r = checkPurchase(app, { title, price, url: context?.url || "" });
    return [`${r.title_text}.`, r.left_this_month != null ? `${r.category_name}: ${money(Math.max(0, r.left_this_month))} left this month.` : "",
      ...r.reasons.slice(0, 2).map((x) => `• ${x}`), r.reasonable_price ? `A reasonable price for you now: up to ${money(r.reasonable_price)}.` : ""].filter(Boolean).join("\n");
  },
  help() {
    return "I'm FinPilot's built-in advisor. Ask about what you spent, what's left this month, upcoming bills, goals, where money leaks, or whether something is worth buying (with its price).";
  },
};

// ------------------------------------------------------------------ entry points

export function answerTopic(app, topic, text = "", context = null) {
  return { topic, reply: ANSWERS[topic](app, text, context) };
}

export function answer(app, text, context = null) {
  if (context?.price && /\b(wait|later|next month|payday)\b/i.test(text)) {
    const r = checkPurchase(app, context);
    const budget = r.budget ? ` and uses ${pct(r.price / r.budget)} of your usual ${money(r.budget)} for ${r.category_name}` : "";
    return { topic: "can_afford", reply: `Now: ${r.title_text.toLowerCase()}.\nFrom ${r.next_month_starts} a fresh month starts${budget}.\nPress Postpone and I'll remind you.`, alternatives: [] };
  }
  const ranked = app.models.intent.proba(text);
  const topic = ranked[0].label;
  const out = answerTopic(app, topic, text, context);
  // Unsure: offer the next likely topics as buttons.
  out.alternatives = ranked[0].p < 0.6 ? ranked.slice(1, 3).map((x) => x.label) : [];
  out.confidence = ranked[0].p;
  return out;
}
