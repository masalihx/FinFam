// The family's data, kept only on this computer (chrome.storage.local).
// One family = one 6-character password (letters and digits). Only a salted hash of it is stored.
import { normalize, withSign } from "./ml.js";
import { addDays, addMonths, monthIndex, todayStr } from "./dates.js";

const SALT_KEY = "finpilot:salt", CURRENT_KEY = "finpilot:current", FAMILY_PREFIX = "finpilot:family:";
export const DEMO_PASSWORD = "DEMO26";

// Inside the extension: chrome.storage.local. On a plain test page: localStorage (or memory with ?memory).
const mem = new Map();
const backend = globalThis.chrome?.storage?.local
  ? { get: async (k) => (await chrome.storage.local.get(k))[k], set: (k, v) => chrome.storage.local.set({ [k]: v }), del: (k) => chrome.storage.local.remove(k) }
  : globalThis.location?.search.includes("memory")
    ? { get: async (k) => (mem.has(k) ? structuredClone(mem.get(k)) : undefined), set: async (k, v) => { mem.set(k, structuredClone(v)); }, del: async (k) => { mem.delete(k); } }
    : { get: async (k) => { const s = localStorage.getItem(k); return s ? JSON.parse(s) : undefined; },
        set: async (k, v) => localStorage.setItem(k, JSON.stringify(v)), del: async (k) => localStorage.removeItem(k) };

export const normalizePassword = (p) => String(p || "").trim().toUpperCase();
export function validPassword(p) {
  return /^[A-Z0-9]{6}$/.test(p) && /[A-Z]/.test(p) && /\d/.test(p);
}
export function generatePassword() {
  const letters = "ABCDEFGHJKLMNPQRSTUVWXYZ", digits = "23456789", all = letters + digits;
  const pick = (s) => s[crypto.getRandomValues(new Uint32Array(1))[0] % s.length];
  const chars = [pick(letters), pick(digits), ...Array.from({ length: 4 }, () => pick(all))];
  for (let i = chars.length - 1; i > 0; i--) { const j = crypto.getRandomValues(new Uint32Array(1))[0] % (i + 1); [chars[i], chars[j]] = [chars[j], chars[i]]; }
  return chars.join("");
}

async function familyKey(password) {
  let salt = await backend.get(SALT_KEY);
  if (!salt) { salt = crypto.randomUUID(); await backend.set(SALT_KEY, salt); }
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(`${salt}:${normalizePassword(password)}`));
  return FAMILY_PREFIX + [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

const uid = () => Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
const byDate = (a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0);

export class Store {
  constructor(models) { this.models = models; this.key = null; this.data = null; }

  get ready() { return !!this.data; }
  async save() { if (this.key) await backend.set(this.key, this.data); }

  // Re-open the family that was unlocked last time on this computer (until "Lock").
  async resume() {
    const key = await backend.get(CURRENT_KEY);
    const data = key ? await backend.get(key) : null;
    if (data) { this.key = key; this.data = data; }
    return this.ready;
  }

  async unlock(password) {
    const key = await familyKey(password);
    const data = await backend.get(key);
    if (!data) throw new Error("No family with this password on this computer.");
    this.key = key; this.data = data;
    await backend.set(CURRENT_KEY, key);
  }

  async lock() { this.key = null; this.data = null; await backend.del(CURRENT_KEY); }

  async createFamily(name, password, children = 0) {
    password = normalizePassword(password);
    if (!validPassword(password)) throw new Error("Password: exactly 6 letters and digits, with at least one of each.");
    const key = await familyKey(password);
    if (await backend.get(key)) throw new Error("This password is already used by another family. Pick another one.");
    this.key = key;
    this.data = { family: { name: name.trim() || "Our family", children: Number(children) || 0, is_demo: false },
      transactions: [], corrections: {}, goals: [], plans: [], postponed: [], settings: {} };
    await this.save();
    await backend.set(CURRENT_KEY, key);
  }

  async deleteFamily() { if (this.key) await backend.del(this.key); await this.lock(); }

  // ---------------------------------------------------------------- transactions

  categorize(items) {
    return items.map((t) => {
      if (t.category) return { ...t, category_source: t.category_source || "user" };
      const text = withSign(t.amount, t.description);
      const fixed = this.data.corrections[normalize(text)];
      return { ...t, category: fixed ? fixed.category : this.models.categorizer.predict(text), category_source: fixed ? "user" : "model" };
    });
  }

  async addTransactions(items, source) {
    const ids = new Set(this.data.transactions.map((t) => t.id));
    const fresh = this.categorize(items.filter((t) => !ids.has(t.id)).map((t) => ({ ...t, source: t.source || source })));
    this.data.transactions.push(...fresh);
    this.data.transactions.sort(byDate);
    await this.save();
    return fresh.length;
  }

  async addEntry({ kind, amount, description, date, category }) {
    const value = Math.abs(Number(amount));
    if (!(value > 0)) throw new Error("Enter an amount above $0.");
    if (!String(description || "").trim()) throw new Error("Write what it was for.");
    const t = { id: `manual-${uid()}`, date: date || todayStr(), amount: kind === "income" ? value : -value, description: description.trim(), channel: "manual" };
    if (category) Object.assign(t, { category, category_source: "user" });
    await this.addTransactions([t], "manual");
  }

  async deleteTransaction(id) { this.data.transactions = this.data.transactions.filter((t) => t.id !== id); await this.save(); }

  applyCorrection(text, category, exceptId = null) {
    const key = normalize(text);
    this.data.corrections[key] = { category, example: text };
    let n = 0;
    for (const t of this.data.transactions) {
      if (t.id !== exceptId && t.category_source === "model" && normalize(withSign(t.amount, t.description)) === key) { t.category = category; n++; }
    }
    return n;
  }

  async fixCategory(txId, category) {
    const t = this.data.transactions.find((x) => x.id === txId);
    if (!t) throw new Error("Transaction not found.");
    const n = this.applyCorrection(withSign(t.amount, t.description), category, txId);
    t.category = category; t.category_source = "user";
    await this.save();
    return n;
  }

  // ---------------------------------------------------------------- postponed, settings, needs/wants

  async postpone(item) {
    const remind = addMonths(todayStr().slice(0, 8) + "01", 1);
    this.data.postponed.unshift({ id: uid(), created_at: todayStr(), remind_on: remind, status: "waiting", ...item });
    await this.save();
    return remind;
  }

  async setPostponedStatus(id, status) {
    const item = this.data.postponed.find((i) => i.id === id);
    if (item) { item.status = status; await this.save(); }
  }

  async addGoal({ name, target, saved = 0, deadline }) {
    target = Number(target); saved = Number(saved) || 0;
    if (!String(name || "").trim()) throw new Error("Name the goal.");
    if (!(target > 0)) throw new Error("Enter a target above $0.");
    if (!deadline || deadline <= todayStr()) throw new Error("Pick a date in the future.");
    this.data.goals.push({ id: uid(), name: name.trim(), target, saved, deadline });
    await this.save();
  }

  async deleteGoal(id) { this.data.goals = this.data.goals.filter((g) => g.id !== id); await this.save(); }

  async setSettings(values) { this.data.settings = { ...this.data.settings, ...values }; await this.save(); }

  limits() { return {}; }
  kindOf(category) { return this.models.needs.has(category) ? "need" : this.models.wants.has(category) ? "want" : "other"; }

  // ---------------------------------------------------------------- demo family (the Carters)

  async loadDemo(demo, today = todayStr()) {
    const existing = await backend.get(await familyKey(DEMO_PASSWORD));
    if (existing) { await this.unlock(DEMO_PASSWORD); return; }
    await this.createFamily(demo.family_name, DEMO_PASSWORD, 2);
    this.data.family.is_demo = true;
    const shift = monthIndex(today) - monthIndex(`${demo.anchor_month}-01`);
    const items = demo.transactions.map((t) => ({ ...t, date: addMonths(t.date, shift),
      category: t.source === "allowance" ? "income" : undefined, category_source: t.source === "allowance" ? "user" : undefined }))
      .filter((t) => t.date <= today);
    this.data.transactions = this.categorize(items).sort(byDate);
    for (const [text, category] of demo.seed_corrections) this.applyCorrection(text, category);
    for (const g of demo.family_goals) this.data.goals.push({ id: uid(), ...g });
    for (const p of demo.plans) this.data.plans.push({ id: uid(), name: p.name, amount: p.amount, date: addDays(today, p.days_ahead) });
    await this.save();
  }
}
