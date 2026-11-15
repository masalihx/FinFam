// The family's data, kept only on this computer (chrome.storage.local).
// Profiles with a PIN and roles (parent / teen); rights are checked here, not only in the UI.
import { normalize, withSign } from "./ml.js";
import { addDays, addMonths, monthIndex, todayStr } from "./dates.js";

const KEY = "finpilot";

// Inside the extension: chrome.storage.local. On a plain test page: localStorage (or memory with ?memory).
const backend = globalThis.chrome?.storage?.local
  ? { get: async () => (await chrome.storage.local.get(KEY))[KEY], set: (v) => chrome.storage.local.set({ [KEY]: v }) }
  : globalThis.location?.search.includes("memory")
    ? { mem: null, async get() { return this.mem; }, async set(v) { this.mem = structuredClone(v); } }
    : { async get() { const s = localStorage.getItem(KEY); return s ? JSON.parse(s) : null; },
        async set(v) { localStorage.setItem(KEY, JSON.stringify(v)); } };

export class Forbidden extends Error {}

async function hashPin(pin, salt) {
  const data = new TextEncoder().encode(`${salt}:${pin}`);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

const uid = () => Math.random().toString(36).slice(2, 10) + Date.now().toString(36);

export class Store {
  constructor(models) { this.models = models; this.data = null; }

  async load() { this.data = (await backend.get()) || null; return this.data; }
  async save() { await backend.set(this.data); }
  get ready() { return !!this.data; }

  // ---------------------------------------------------------------- family and profiles

  async createFamily(name, members) {
    const salt = uid();
    this.data = { family: { name, salt, setup_done: false, needs_wants: {}, is_demo: false }, members: [], transactions: [],
      corrections: {}, goals: [], plans: [], postponed: [], settings: {}, price_cache: {}, current: null };
    for (const m of members) await this.addMember(m, true);
    await this.save();
  }

  async addMember({ name, role, pin, key = null, allowance = null }, skipCheck = false) {
    if (!skipCheck) this.requireParent();
    if (!["parent", "teen"].includes(role)) throw new Error("Role must be parent or teen.");
    if (!/^\d{4}$/.test(String(pin))) throw new Error("PIN must be 4 digits.");
    const id = this.data.members.length + 1;
    this.data.members.push({ id, key, name, role, pin_hash: await hashPin(pin, this.data.family.salt), paypal_email: null,
      allowance_amount: allowance ? allowance[0] : null, allowance_period: allowance ? allowance[1] : null });
    return id;
  }

  members() { return this.data.members.map(({ pin_hash, ...m }) => m); }
  member(id) { return this.members().find((m) => m.id === id); }
  get me() { return this.data?.current ? this.member(this.data.current) : null; }

  async login(memberId, pin) {
    const m = this.data.members.find((x) => x.id === memberId);
    if (!m || m.pin_hash !== (await hashPin(pin, this.data.family.salt))) throw new Error("Wrong PIN.");
    this.data.current = memberId;
    await this.save();
    return this.me;
  }
  async logout() { this.data.current = null; await this.save(); }

  requireMe() { if (!this.me) throw new Forbidden("Choose your profile first."); return this.me; }
  requireParent() { if (this.requireMe().role !== "parent") throw new Forbidden("Only parents can do this."); }

  // ---------------------------------------------------------------- transactions

  categorize(items) {
    return items.map((t) => {
      if (t.category) return { ...t, category_source: t.category_source || "file" };
      const text = withSign(t.amount, t.description);
      const fixed = this.data.corrections[normalize(text)];
      return { ...t, category: fixed ? fixed.category : this.models.categorizer.predict(text), category_source: "model" };
    });
  }

  async addTransactions(items, memberId, source) {
    const ids = new Set(this.data.transactions.map((t) => t.id));
    const fresh = this.categorize(items.filter((t) => !ids.has(t.id)).map((t) => ({ ...t, member_id: t.member_id ?? memberId, source: t.source || source })));
    this.data.transactions.push(...fresh);
    this.data.transactions.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
    await this.save();
    return fresh.length;
  }

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
    this.requireMe();
    const t = this.data.transactions.find((x) => x.id === txId);
    if (!t) throw new Error("Transaction not found.");
    const n = this.applyCorrection(withSign(t.amount, t.description), category, txId);
    t.category = category; t.category_source = "user";
    await this.save();
    return n;
  }

  // ---------------------------------------------------------------- goals, plans, postponed, setup

  async addGoal({ name, target, saved = 0, deadline, personal }) {
    const me = this.requireMe();
    if (!personal) this.requireParent();
    this.data.goals.push({ id: uid(), member_id: personal ? me.id : null, name, target: +target, saved: +saved, deadline });
    await this.save();
  }
  editableGoal(id) {
    const me = this.requireMe(), g = this.data.goals.find((x) => x.id === id);
    if (!g) throw new Error("Goal not found.");
    if (me.role !== "parent" && g.member_id !== me.id) throw new Forbidden(g.member_id ? "This is someone else's goal." : "Only parents can change family goals.");
    return g;
  }
  async addToGoal(id, amount) { const g = this.editableGoal(id); g.saved = Math.max(0, g.saved + +amount); await this.save(); }
  async deleteGoal(id) { this.editableGoal(id); this.data.goals = this.data.goals.filter((g) => g.id !== id); await this.save(); }

  async addPlan({ name, amount, date }) {
    this.data.plans.push({ id: uid(), member_id: this.requireMe().id, name, amount: +amount, date });
    await this.save();
  }
  async deletePlan(id) { this.requireMe(); this.data.plans = this.data.plans.filter((p) => p.id !== id); await this.save(); }

  async postpone(item) {
    const me = this.requireMe();
    const remind = addMonths(todayStr().slice(0, 8) + "01", 1);
    this.data.postponed.unshift({ id: uid(), member_id: me.id, created_at: todayStr(), remind_on: remind, status: "waiting", ...item });
    await this.save();
    return remind;
  }
  async setPostponedStatus(id, status) { this.requireMe(); const p = this.data.postponed.find((x) => x.id === id); if (p) p.status = status; await this.save(); }

  async saveSetup(items) {
    this.requireParent();
    this.data.family.needs_wants = Object.fromEntries(items.map((i) => [i.category, { kind: i.kind, limit: i.kind === "want" ? i.monthly_limit : null }]));
    this.data.family.setup_done = true;
    await this.save();
  }
  limits() { return Object.fromEntries(Object.entries(this.data.family.needs_wants).filter(([, v]) => v.kind === "want" && v.limit != null).map(([c, v]) => [c, v.limit])); }
  kindOf(category) {
    const set = this.data.family.needs_wants[category];
    if (set) return set.kind;
    return this.models.needs.has(category) ? "need" : this.models.wants.has(category) ? "want" : "other";
  }

  async setAllowance(memberId, amount, period) {
    this.requireParent();
    const m = this.data.members.find((x) => x.id === memberId);
    Object.assign(m, { allowance_amount: +amount, allowance_period: period });
    await this.save();
  }
  async payAllowance(memberId, channel = "internal") {
    this.requireParent();
    const teen = this.data.members.find((x) => x.id === memberId);
    if (!teen?.allowance_amount) throw new Error("Set the allowance amount first.");
    const today = todayStr(), stamp = uid(), me = this.me;
    this.data.transactions.push(
      { id: `allow-in-${stamp}`, date: today, amount: teen.allowance_amount, description: `ALLOWANCE FROM ${me.name.toUpperCase()}`, member_id: teen.id, category: "income", category_source: "user", source: "allowance", channel },
      { id: `allow-out-${stamp}`, date: today, amount: -teen.allowance_amount, description: `ALLOWANCE TO ${teen.name.toUpperCase()}`, member_id: me.id, category: "transfer", category_source: "user", source: "allowance", channel });
    await this.save();
  }
  async setPaypalEmail(memberId, email) {
    const me = this.requireMe();
    if (memberId !== me.id) this.requireParent();
    this.data.members.find((x) => x.id === memberId).paypal_email = email.trim().toLowerCase() || null;
    await this.save();
  }
  async setSettings(values) { this.data.settings = { ...this.data.settings, ...values }; await this.save(); }

  // ---------------------------------------------------------------- demo family (the Carters)

  async loadDemo(demo, today = todayStr()) {
    const shift = monthIndex(today) - monthIndex(`${demo.anchor_month}-01`);
    await this.createFamily(demo.family_name, demo.members.map((m) => ({ name: m.name, role: m.role, pin: demo.pins[m.key], key: m.key, allowance: m.allowance })));
    this.data.family.is_demo = true;
    const ids = Object.fromEntries(this.data.members.map((m) => [m.key, m.id]));
    const items = demo.transactions.map((t) => ({ ...t, date: addMonths(t.date, shift), member_id: ids[t.member],
      category: t.source === "allowance" ? "income" : undefined, category_source: t.source === "allowance" ? "user" : undefined }))
      .filter((t) => t.date <= today);
    this.data.transactions = this.categorize(items).sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
    for (const [text, category] of demo.seed_corrections) this.applyCorrection(text, category);
    for (const g of demo.family_goals) this.data.goals.push({ id: uid(), member_id: null, ...g });
    for (const [key, goals] of Object.entries(demo.personal_goals)) for (const g of goals) this.data.goals.push({ id: uid(), member_id: ids[key], ...g });
    for (const p of demo.plans) this.data.plans.push({ id: uid(), member_id: p.member ? ids[p.member] : null, name: p.name, amount: p.amount, date: addDays(today, p.days_ahead) });
    await this.save();
  }
}
