// FinPilot background worker: the only part that talks to the family's FinPilot platform.
// Shop pages never call the platform directly; they ask this worker, which adds the login token.

const DEFAULT_API = "http://localhost:8000";

async function settings() {
  const s = await chrome.storage.local.get(["apiBase", "token", "who"]);
  return { apiBase: (s.apiBase || DEFAULT_API).replace(/\/+$/, ""), token: s.token || "", who: s.who || null };
}

async function call(path, method = "GET", body) {
  const { apiBase, token } = await settings();
  let res;
  try {
    res = await fetch(apiBase + path, {
      method,
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    throw new Error(`Cannot reach FinPilot at ${apiBase}. Is the platform running?`);
  }
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) throw new Error("Log in to FinPilot from the extension popup first.");
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : `FinPilot error ${res.status}`);
  return data;
}

async function saveLogin(data) {
  await chrome.storage.local.set({ token: data.token });
  const me = await call("/api/me");
  await chrome.storage.local.set({ who: { name: me.user.name, role: me.member?.role, room: me.member?.room_name } });
  return me;
}

const ROUTES = {
  me: () => call("/api/me"),
  login: async (m) => saveLogin(await call("/api/auth/login", "POST", { email: m.email, password: m.password })),
  demoLogin: async (m) => saveLogin(await call(`/api/demo/login?who=${encodeURIComponent(m.who || "alex")}`, "POST")),
  logout: async () => { await chrome.storage.local.remove(["token", "who"]); return { ok: true }; },
  check: (m) => call("/api/check-purchase", "POST", m.product),
  postpone: (m) => call("/api/postpone", "POST", m.product),
  chat: (m) => call("/api/chat", "POST", { message: m.message, context: m.context }),
  openPlatform: async (m) => {
    chrome.tabs.create({ url: (await settings()).apiBase + (m.path || "/") });
    return { ok: true };
  },
};

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  const route = ROUTES[msg?.type];
  if (!route) return false;
  route(msg).then((data) => sendResponse({ ok: true, data })).catch((e) => sendResponse({ ok: false, error: e.message }));
  return true; // answer arrives asynchronously
});

// Select a product name and its price on any page, right-click: "Is this worth it? (FinPilot)".
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({ id: "finpilot-check", title: "Is this worth it? (FinPilot)", contexts: ["selection"] });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "finpilot-check" && tab?.id) {
    chrome.tabs.sendMessage(tab.id, { type: "checkSelection", text: info.selectionText || "" });
  }
});
