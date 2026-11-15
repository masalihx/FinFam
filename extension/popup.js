const $ = (id) => document.getElementById(id);
const send = (msg) => new Promise((resolve) => chrome.runtime.sendMessage(msg, (r) => resolve(r || { ok: false, error: "No answer" })));
let tab = null;

async function render() {
  const s = await chrome.storage.local.get(["apiBase", "who"]);
  $("api").value = s.apiBase || "http://localhost:8000";
  const me = await send({ type: "me" });
  const signedIn = me.ok && me.data.member;
  $("signed-in").hidden = !signedIn;
  $("signed-out").hidden = signedIn;
  $("logout").hidden = !signedIn;
  $("who").innerHTML = signedIn ? `<b>${me.data.user.name}</b><br>${me.data.member.role} · ${me.data.member.room_name}` : (me.ok ? "" : "not connected");
  if (!signedIn) return;
  [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) return;
  chrome.tabs.sendMessage(tab.id, { type: "getProduct" }, (res) => {
    if (chrome.runtime.lastError || !res) { $("found").textContent = "Cannot read this page. Type the product and price."; return; }
    if (res.product) {
      $("title").value = res.product.title;
      $("price").value = res.product.price;
      $("found").textContent = `Found on the page (${res.product.source}).`;
    } else {
      $("title").value = res.title || "";
      $("found").textContent = "No price found automatically. Type it, or select the product and price on the page → right-click → “Is this worth it?”.";
    }
  });
}

$("login").addEventListener("submit", async (e) => {
  e.preventDefault();
  const r = await send({ type: "login", email: $("email").value, password: $("password").value });
  $("login-err").textContent = r.ok ? "" : r.error;
  if (r.ok) render();
});
document.querySelectorAll("[data-demo]").forEach((b) => b.addEventListener("click", async () => {
  const r = await send({ type: "demoLogin", who: b.dataset.demo });
  $("login-err").textContent = r.ok ? "" : r.error;
  if (r.ok) render();
}));
$("check").addEventListener("click", () => {
  const price = Number($("price").value);
  if (!(price > 0) || !tab?.id) return;
  chrome.tabs.sendMessage(tab.id, { type: "checkManual", product: { title: $("title").value, price, url: tab.url } });
  window.close();
});
$("open").addEventListener("click", () => send({ type: "openPlatform", path: "/" }));
$("logout").addEventListener("click", async () => { await send({ type: "logout" }); render(); });
$("save").addEventListener("click", async () => {
  await chrome.storage.local.set({ apiBase: $("api").value.trim() || "http://localhost:8000" });
  $("save").textContent = "Saved ✓";
  render();
});
$("chat").addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = $("q").value.trim();
  if (!q) return;
  $("answer").hidden = false;
  $("answer").textContent = "…";
  const r = await send({ type: "chat", message: q });
  $("answer").textContent = r.ok ? r.data.reply : r.error;
});

render();
