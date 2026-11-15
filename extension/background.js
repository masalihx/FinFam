// FinPilot background worker: the only part that talks to the FinPilot platform.
// Shop pages never call the platform directly; they ask this worker.

const DEFAULT_API = "http://localhost:8000";

async function apiBase() {
  const { apiBase } = await chrome.storage.sync.get("apiBase");
  return (apiBase || DEFAULT_API).replace(/\/+$/, "");
}

async function call(path, method = "GET", body) {
  const base = await apiBase();
  let res;
  try {
    res = await fetch(base + path, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    throw new Error(`Cannot reach FinPilot at ${base}. Is the platform running?`);
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `FinPilot error ${res.status}`);
  return data;
}

const ROUTES = {
  status: () => call("/api/status"),
  check: (m) => call("/api/check-purchase", "POST", m.product),
  postpone: (m) => call("/api/postpone", "POST", m.product),
  chat: (m) => call("/api/chat", "POST", { message: m.message, context: m.context }),
  openPlatform: async () => {
    chrome.tabs.create({ url: (await apiBase()) + "/#postponed" });
    return { ok: true };
  },
};

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  const route = ROUTES[msg?.type];
  if (!route) return false;
  route(msg)
    .then((data) => sendResponse({ ok: true, data }))
    .catch((e) => sendResponse({ ok: false, error: e.message }));
  return true; // keep the channel open for the async answer
});

// Right-click a selected price on any page: "Check this price with FinPilot".
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({ id: "finpilot-check", title: "Check this price with FinPilot", contexts: ["selection"] });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "finpilot-check" && tab?.id) {
    chrome.tabs.sendMessage(tab.id, { type: "checkSelection", text: info.selectionText || "" });
  }
});
