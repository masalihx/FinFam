// FinPilot background worker: runs the same engine as the side panel for the on-page card.
// No server: models are files inside the extension, data is chrome.storage.local.
import { loadModels } from "./lib/ml.js";
import { Store } from "./lib/store.js";
import { todayStr } from "./lib/dates.js";
import { checkPurchase } from "./lib/verdict.js";
import { answer } from "./lib/assistant.js";

let modelsPromise = null;
async function app() {
  modelsPromise ||= loadModels(chrome.runtime.getURL(""));
  const models = await modelsPromise;
  const store = new Store(models);
  await store.load(); // always fresh: the panel may have changed the data
  if (!store.ready) throw new Error("Open FinPilot (toolbar icon) and set up your family first.");
  if (!store.me) throw new Error("Open FinPilot (toolbar icon) and choose your profile.");
  return { models, store, today: todayStr() };
}

const ROUTES = {
  async check(msg) { return checkPurchase(await app(), msg.product); },
  async chat(msg) { const a = await app(); return answer(a, msg.message, msg.context, [], chrome.runtime.getURL("")); },
  async postpone(msg) { const a = await app(); return { remind_on: await a.store.postpone(msg.product) }; },
  async openPanel(msg, sender) { await chrome.sidePanel.open({ tabId: sender.tab.id }); return { ok: true }; },
};

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  const route = ROUTES[msg?.type];
  if (!route) return false;
  route(msg, sender).then((data) => sendResponse({ ok: true, data })).catch((e) => sendResponse({ ok: false, error: e.message }));
  return true;
});

chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
  chrome.contextMenus.create({ id: "finpilot-check", title: "Is this worth it? (FinPilot)", contexts: ["selection"] });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "finpilot-check" && tab?.id) chrome.tabs.sendMessage(tab.id, { type: "checkSelection", text: info.selectionText || "" });
});
