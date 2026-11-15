// FinPilot side panel: first run, profile picker, shell and router.
import { loadModels } from "./lib/ml.js";
import { Store } from "./lib/store.js";
import { todayStr } from "./lib/dates.js";
import { $, $$, avatar, busy, esc, formData, toast } from "./lib/ui.js";
import { VIEWS, TABS } from "./views/index.js";

const root = $("#root");
const app = { models: null, store: null, today: todayStr(), refresh: () => route() };

// ------------------------------------------------------------------ first run

function renderOnboarding() {
  root.innerHTML = `
    <div class="center">
      <div style="display:flex;align-items:center;gap:8px"><span class="logo">F</span><b>FinPilot</b></div>
      <h1 style="margin-top:16px">Your family's money copilot</h1>
      <p class="muted">Before you click Buy, FinPilot checks your family budget, your usual prices and market prices. Everything stays on this computer.</p>
      <button class="btn primary block" id="demo" style="margin-top:8px">Try the demo family (the Carters)</button>
      <p class="xs muted">2 parents, 2 teens. Synthetic bank data from an open dataset (Misata, CC BY 4.0) plus generated teen spending. PINs: Alex 1111, Sam 2222, Maya 3333, Leo 4444.</p>
      <div class="section" style="margin-top:16px">
        <h2>Create your family</h2>
        <form id="create" class="stack" style="margin-top:12px">
          <label class="field">Family name<input class="input" name="family" required placeholder="The Smith family"></label>
          <div id="people"></div>
          <button type="button" class="btn ghost sm" id="add-person">+ Add a family member</button>
          <button class="btn primary block">Create family</button>
        </form>
      </div>
    </div>`;
  const people = $("#people");
  const addRow = (role = "teen") => {
    const i = people.children.length;
    people.insertAdjacentHTML("beforeend", `
      <fieldset class="grid2" style="border:0;padding:0;margin:0 0 8px;grid-template-columns:1.4fr 1fr .8fr">
        <legend class="sr-only">Member ${i + 1}</legend>
        <label class="field">Name<input class="input" name="name${i}" required></label>
        <label class="field">Role<select class="select" name="role${i}"><option value="parent" ${role === "parent" ? "selected" : ""}>Parent</option><option value="teen" ${role === "teen" ? "selected" : ""}>Teen</option></select></label>
        <label class="field">PIN<input class="input" name="pin${i}" inputmode="numeric" pattern="\\d{4}" maxlength="4" required></label>
      </fieldset>`);
  };
  addRow("parent");
  $("#add-person").addEventListener("click", () => addRow());
  $("#demo").addEventListener("click", (e) => busy(e.currentTarget, async () => {
    const demo = await (await fetch("data/demo_family.json")).json();
    await app.store.loadDemo(demo, app.today);
    start();
  }));
  $("#create").addEventListener("submit", (e) => {
    e.preventDefault();
    const f = formData(e.target);
    const members = [...people.children].map((_, i) => ({ name: f[`name${i}`], role: f[`role${i}`], pin: f[`pin${i}`] }));
    if (!members.some((m) => m.role === "parent")) return toast("A family needs at least one parent.");
    busy(e.submitter, async () => { await app.store.createFamily(f.family, members); start(); });
  });
}

// ------------------------------------------------------------------ profile picker

function renderPicker() {
  const s = app.store;
  root.innerHTML = `
    <div class="center">
      <h1>Who's using FinPilot?</h1>
      <p class="muted">${esc(s.data.family.name)}</p>
      <div class="people">${s.members().map((m, i) => `
        <button class="person" data-id="${m.id}">${avatar(m.name, i, "lg")}<b>${esc(m.name)}</b><span class="xs muted">${m.role === "parent" ? "Parent" : "Teen"}</span></button>`).join("")}</div>
    </div>`;
  $$(".person").forEach((b) => b.addEventListener("click", () => askPin(Number(b.dataset.id))));
}

function askPin(id) {
  const m = app.store.member(id);
  root.innerHTML = `
    <div class="center" style="text-align:center">
      <h1>Hi, ${esc(m.name)}</h1><p class="muted">Enter your 4-digit PIN</p>
      <div class="pin"><input id="pin" type="password" inputmode="numeric" maxlength="4" autocomplete="off" aria-label="4-digit PIN"
        style="width:160px;letter-spacing:12px;text-align:center"></div>
      <button class="btn ghost" id="back">Back</button>
    </div>`;
  const input = $("#pin");
  input.focus();
  input.addEventListener("input", async () => {
    input.value = input.value.replace(/\D/g, "").slice(0, 4);
    if (input.value.length < 4) return;
    try { await app.store.login(id, input.value); start(); } catch (e) { toast(e.message); input.value = ""; input.focus(); }
  });
  $("#back").addEventListener("click", renderPicker);
}

// ------------------------------------------------------------------ shell and router

function renderShell() {
  const s = app.store, me = s.me;
  const idx = s.members().findIndex((m) => m.id === me.id);
  root.innerHTML = `
    <header class="topbar">
      <span class="logo">F</span>
      <div><div class="family">${esc(s.data.family.name)}</div><div class="sub">${s.data.family.is_demo ? "Demo family · " : ""}prototype, not financial advice</div></div>
      <button class="profile-chip" id="switch" aria-label="Switch profile">${avatar(me.name, idx)}${esc(me.name)}</button>
    </header>
    <main id="view"></main>
    <nav class="tabbar" aria-label="Main">${TABS.map((t) => `<button data-tab="${t.id}"><span class="ico" aria-hidden="true">${t.icon}</span>${t.label}</button>`).join("")}</nav>`;
  $("#switch").addEventListener("click", async () => { await s.logout(); renderPicker(); });
  $$("[data-tab]").forEach((b) => b.addEventListener("click", () => { location.hash = b.dataset.tab; }));
}

async function route() {
  if (!app.store.me) return;
  const [id, query] = (location.hash.slice(1) || "home").split("?");
  const view = VIEWS[id] ? id : "home";
  const tab = TABS.find((t) => t.id === view || (t.children || []).includes(view))?.id;
  $$("[data-tab]").forEach((b) => (b.dataset.tab === tab ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current")));
  const el = $("#view");
  el.innerHTML = `<div class="skeleton" style="height:22px;width:50%"></div><div class="skeleton" style="height:90px;margin-top:12px"></div>`;
  try {
    await VIEWS[view](el, app, new URLSearchParams(query || ""));
  } catch (e) {
    console.error(e);
    el.innerHTML = `<div class="section" role="alert"><h2>Something went wrong</h2><p class="muted">${esc(e.message)}</p><button class="btn ghost" id="retry">Try again</button></div>`;
    $("#retry").addEventListener("click", route);
  }
  window.scrollTo(0, 0);
}
window.addEventListener("hashchange", route);

function start() {
  if (!app.store.ready) return renderOnboarding();
  if (!app.store.me) return renderPicker();
  renderShell();
  route();
}

(async () => {
  app.models = await loadModels("");
  app.store = new Store(app.models);
  await app.store.load();
  start();
})().catch((e) => { root.innerHTML = `<div class="center" role="alert"><h1>FinPilot could not start</h1><p class="muted">${esc(e.message)}</p></div>`; });
