// FinPilot on shop pages: finds the product, asks the platform, shows the verdict.
(function () {
  if (window.__finpilotLoaded) return;
  window.__finpilotLoaded = true;

  // Do not run on the FinPilot platform itself.
  if (/^(localhost|127\.0\.0\.1)$/.test(location.hostname) && location.port === "8000" && !location.pathname.includes("demo-")) return;

  const ICON = { red: "🔴", yellow: "🟡", green: "🟢" };
  const TITLE = { red: "Better to postpone", yellow: "Think it over", green: "Looks fine" };
  const money = (x) => "$" + Number(x).toLocaleString("en-US", { maximumFractionDigits: 2 });
  const pct = (p) => (p == null ? "—" : Math.round(p * 100) + "%");

  let host, root, lastKey = null, product = null, verdict = null;

  function send(msg) {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage(msg, (res) => resolve(res || { ok: false, error: "No answer from FinPilot" }));
      } catch (e) {
        resolve({ ok: false, error: "Extension was reloaded. Refresh the page." });
      }
    });
  }

  function ensureRoot() {
    if (root) return root;
    host = document.createElement("div");
    host.id = "finpilot-root";
    host.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:2147483647;";
    document.documentElement.appendChild(host);
    root = host.attachShadow({ mode: "open" });
    root.innerHTML = `<style>
      * { box-sizing: border-box; font-family: Inter, system-ui, -apple-system, "Segoe UI", sans-serif; }
      .pill { display:flex; align-items:center; gap:8px; background:#0f172a; color:#fff; border-radius:999px; padding:9px 14px;
              font-size:13px; cursor:pointer; box-shadow:0 8px 24px rgba(15,23,42,.25); border:none; }
      .card { width:340px; background:#fff; color:#0f172a; border-radius:16px; box-shadow:0 12px 40px rgba(15,23,42,.25);
              border:1px solid #e2e8f0; overflow:hidden; font-size:14px; line-height:1.45; }
      .head { padding:12px 14px; display:flex; justify-content:space-between; align-items:flex-start; gap:8px; }
      .red .head { background:#fef2f2; } .yellow .head { background:#fffbeb; } .green .head { background:#f0fdf4; }
      .verdict { font-weight:700; font-size:16px; }
      .product { color:#475569; font-size:12px; margin-top:2px; }
      .x { border:none; background:transparent; font-size:16px; color:#64748b; cursor:pointer; }
      .body { padding:12px 14px; }
      .reason { margin:0 0 8px; }
      .meter { font-size:12px; color:#475569; }
      .bar { height:6px; background:#f1f5f9; border-radius:999px; margin-top:4px; overflow:hidden; }
      .bar > div { height:100%; border-radius:999px; }
      .row { display:flex; gap:8px; margin-top:12px; flex-wrap:wrap; }
      button.main { background:#0f766e; color:#fff; border:none; border-radius:10px; padding:8px 12px; font-size:13px; cursor:pointer; }
      button.sec { background:#fff; color:#0f172a; border:1px solid #cbd5e1; border-radius:10px; padding:7px 11px; font-size:13px; cursor:pointer; }
      .foot { padding:8px 14px; font-size:11px; color:#64748b; border-top:1px solid #f1f5f9; display:flex; justify-content:space-between; }
      .chat { margin-top:10px; display:none; }
      .chat.open { display:block; }
      .chat form { display:flex; gap:6px; }
      .chat input { flex:1; border:1px solid #cbd5e1; border-radius:10px; padding:7px 9px; font-size:13px; }
      .answer { background:#f1f5f9; border-radius:10px; padding:8px 10px; margin-top:8px; font-size:13px; white-space:pre-line; }
      .warn { font-size:12px; color:#92400e; background:#fef3c7; border-radius:8px; padding:6px 8px; margin-bottom:8px; }
      a { color:#0f766e; }
    </style><div id="box"></div>`;
    return root;
  }

  function box() {
    return ensureRoot().getElementById("box");
  }

  function showPill(text) {
    box().innerHTML = `<button class="pill" id="open">${text}</button>`;
    box().querySelector("#open").addEventListener("click", showCard);
  }

  function showLoading() {
    box().innerHTML = `<button class="pill">FinPilot · checking your budget…</button>`;
  }

  function showError(error) {
    box().innerHTML = `<button class="pill" id="open" title="${escapeHtml(error)}">FinPilot · offline</button>`;
    box().querySelector("#open").addEventListener("click", () => {
      box().innerHTML = `<div class="card"><div class="head"><div><div class="verdict">FinPilot is not connected</div>
        <div class="product">${escapeHtml(error)}</div></div><button class="x" id="x">✕</button></div>
        <div class="body">Start the platform (<code>uvicorn backend.main:app --port 8000</code>) and load your data, then refresh this page.</div></div>`;
      box().querySelector("#x").addEventListener("click", () => showError(error));
    });
  }

  function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function showCard() {
    const v = verdict;
    const color = { red: "#dc2626", yellow: "#d97706", green: "#16a34a" }[v.light];
    const nonUsd = product.currency && product.currency !== "USD";
    box().innerHTML = `
      <div class="card ${v.light}">
        <div class="head">
          <div>
            <div class="verdict">${ICON[v.light]} ${TITLE[v.light]}</div>
            <div class="product">${escapeHtml(product.title.slice(0, 70))} · ${money(product.price)} · ${escapeHtml(v.category_name)}</div>
          </div>
          <button class="x" id="min" title="Minimize">–</button>
        </div>
        <div class="body">
          ${nonUsd ? `<div class="warn">Price is in ${escapeHtml(product.currency)}; your FinPilot budget is in USD. Check it from the popup with the USD amount.</div>` : ""}
          <p class="reason">${escapeHtml(v.reason)}</p>
          ${v.probability_after != null ? `
          <div class="meter">Chance of overspending ${escapeHtml(v.category_name)} this month: ${pct(v.probability_before)} → <b>${pct(v.probability_after)}</b></div>
          <div class="bar"><div style="width:${Math.round(v.probability_after * 100)}%;background:${color}"></div></div>` : ""}
          <div class="row">
            <button class="main" id="postpone">Postpone</button>
            <button class="sec" id="ask">Ask assistant</button>
            <button class="sec" id="dismiss">Buy anyway</button>
          </div>
          <div class="chat" id="chat">
            <form id="chat-form"><input id="q" placeholder="e.g. What if I wait until payday?" autocomplete="off"><button class="main">Ask</button></form>
            <div id="answers"></div>
          </div>
        </div>
        <div class="foot"><span>Prototype, not financial advice</span><a href="#" id="platform">Open FinPilot</a></div>
      </div>`;
    const $ = (id) => box().querySelector(id);
    $("#min").addEventListener("click", () => showPill(`${ICON[v.light]} FinPilot · ${TITLE[v.light]}`));
    $("#dismiss").addEventListener("click", () => showPill(`${ICON[v.light]} FinPilot`));
    $("#platform").addEventListener("click", (e) => { e.preventDefault(); send({ type: "openPlatform" }); });
    $("#postpone").addEventListener("click", async () => {
      const res = await send({ type: "postpone", product: { ...product, category: v.category, probability: v.probability_after } });
      $("#postpone").textContent = res.ok ? `Postponed ✓ reminder ${res.data.remind_on}` : "Could not save";
      $("#postpone").disabled = true;
    });
    $("#ask").addEventListener("click", () => { $("#chat").classList.add("open"); $("#q").focus(); });
    $("#chat-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const q = $("#q").value.trim();
      if (!q) return;
      $("#q").value = "";
      const div = document.createElement("div");
      div.className = "answer";
      div.textContent = "…";
      $("#answers").prepend(div);
      const res = await send({ type: "chat", message: q, context: { title: product.title, price: product.price, url: product.url, category: v.category } });
      div.textContent = res.ok ? res.data.reply : res.error;
    });
  }

  async function check(p) {
    product = p;
    showLoading();
    const res = await send({ type: "check", product: { title: p.title, price: p.price, url: p.url } });
    if (!res.ok) return showError(res.error);
    verdict = res.data;
    if (verdict.light === "green") showPill(`${ICON.green} FinPilot · ${TITLE.green}`);
    else showCard();
  }

  function scan() {
    const p = window.FinPilotDetect.detectProduct(document);
    const key = p ? `${location.href}|${p.price}` : null;
    if (!p || key === lastKey) return;
    lastKey = key;
    check(p);
  }

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg.type === "getProduct") {
      sendResponse({ product: window.FinPilotDetect.detectProduct(document), url: location.href, title: document.title });
    } else if (msg.type === "checkSelection") {
      const price = window.FinPilotDetect.parsePrice(msg.text);
      if (price) check({ title: document.title, price, url: location.href, currency: window.FinPilotDetect.currencyOf(msg.text) });
    } else if (msg.type === "checkManual") {
      check(msg.product);
    }
    return false;
  });

  // Shops often load prices late and change pages without reloading.
  scan();
  setTimeout(scan, 1500);
  setTimeout(scan, 4000);
  let lastUrl = location.href;
  setInterval(() => {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      lastKey = null;
      setTimeout(scan, 1200);
    }
  }, 1000);
})();
