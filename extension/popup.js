const $ = (id) => document.getElementById(id);
const send = (msg) => new Promise((resolve) => chrome.runtime.sendMessage(msg, (r) => resolve(r || { ok: false, error: "No answer" })));

let tab = null;

async function init() {
  const { apiBase } = await chrome.storage.sync.get("apiBase");
  $("api").value = apiBase || "http://localhost:8000";

  const s = await send({ type: "status" });
  if (s.ok) {
    $("status").textContent = s.data.transactions ? `${s.data.transactions} transactions` : "no data yet";
    $("status").className = "status " + (s.data.transactions ? "ok" : "");
  } else {
    $("status").textContent = "offline";
    $("status").className = "status bad";
  }

  [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) return;
  chrome.tabs.sendMessage(tab.id, { type: "getProduct" }, (res) => {
    if (chrome.runtime.lastError || !res) {
      $("found").textContent = "Cannot read this page. Enter the product and price by hand.";
      return;
    }
    if (res.product) {
      $("title").value = res.product.title;
      $("price").value = res.product.price;
      $("found").textContent = `Found automatically (${res.product.source}${res.product.currency && res.product.currency !== "USD" ? ", price in " + res.product.currency : ""}).`;
    } else {
      $("title").value = res.title || "";
      $("found").textContent = "No price found automatically. Type it, or select the price on the page, right-click → Check this price with FinPilot.";
    }
  });
}

$("check").addEventListener("click", () => {
  const price = Number($("price").value);
  if (!(price > 0) || !tab?.id) return;
  chrome.tabs.sendMessage(tab.id, { type: "checkManual", product: { title: $("title").value, price, url: tab.url, currency: "USD" } });
  window.close();
});

$("open").addEventListener("click", () => send({ type: "openPlatform" }));

$("save").addEventListener("click", async () => {
  await chrome.storage.sync.set({ apiBase: $("api").value.trim() || "http://localhost:8000" });
  $("save").textContent = "Saved ✓";
  init();
});

$("chat-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = $("q").value.trim();
  if (!q) return;
  $("answer").hidden = false;
  $("answer").textContent = "…";
  const res = await send({ type: "chat", message: q });
  $("answer").textContent = res.ok ? res.data.reply : res.error;
});

init();
