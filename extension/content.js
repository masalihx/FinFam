// FinPilot on shop pages: finds the product (or uses your selection), asks the platform, shows the verdict.
(function () {
  if (window.__finpilotLoaded) return;
  window.__finpilotLoaded = true;
  // Do not run on the FinPilot platform itself (except its local demo product page).
  if (/^(localhost|127\.0\.0\.1)$/.test(location.hostname) && location.port === "8000" && !location.pathname.includes("demo-")) return;

  const D = {
    buy: { icon: "🟢", bg: "#f0fdf4", line: "#bbf7d0", bar: "#16a34a" },
    think: { icon: "🟡", bg: "#fffbeb", line: "#fde68a", bar: "#d97706" },
    not_worth_it: { icon: "🔴", bg: "#fef2f2", line: "#fecaca", bar: "#dc2626" },
  };
  const money = (x) => "$" + Number(x).toLocaleString("en-US", { maximumFractionDigits: 2 });
  const pct = (p) => (p == null ? "—" : Math.round(p * 100) + "%");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let root, lastKey = null, product = null, verdict = null;

  function send(msg) {
    return new Promise((resolve) => {
      try { chrome.runtime.sendMessage(msg, (res) => resolve(res || { ok: false, error: "No answer from FinPilot" })); }
      catch (e) { resolve({ ok: false, error: "The extension was reloaded. Refresh this page." }); }
    });
  }

  function box() {
    if (!root) {
      const host = document.createElement("div");
      host.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:2147483647;";
      document.documentElement.appendChild(host);
      root = host.attachShadow({ mode: "open" });
      root.innerHTML = `<style>
        *{box-sizing:border-box;font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif}
        .pill{display:flex;align-items:center;gap:8px;background:#0f172a;color:#fff;border:none;border-radius:999px;padding:10px 15px;font-size:13px;font-weight:600;cursor:pointer;box-shadow:0 10px 30px rgba(15,23,42,.3)}
        .card{width:360px;background:#fff;color:#0f172a;border-radius:18px;box-shadow:0 18px 50px rgba(15,23,42,.3);border:1px solid #e2e8f0;overflow:hidden;font-size:14px;line-height:1.45}
        .head{padding:14px 16px;display:flex;justify-content:space-between;gap:10px;align-items:flex-start}
        .title{font-weight:800;font-size:18px}.sub{color:#475569;font-size:12px;margin-top:2px}
        .x{border:none;background:transparent;font-size:18px;color:#64748b;cursor:pointer;line-height:1}
        .body{padding:12px 16px}
        .fair{display:flex;justify-content:space-between;align-items:center;background:#f8fafc;border-radius:12px;padding:10px 12px;margin-bottom:10px}
        .fair b{font-size:18px}
        ul{margin:0;padding-left:18px}li{margin:4px 0}
        .meter{font-size:12px;color:#475569;margin-top:10px}.bar{height:6px;background:#eef2f6;border-radius:999px;margin-top:5px;overflow:hidden}.bar>div{height:100%;border-radius:999px}
        .market{font-size:12px;color:#475569;margin-top:8px}
        .row{display:flex;gap:8px;margin-top:12px;flex-wrap:wrap}
        .main{background:#0f766e;color:#fff;border:none;border-radius:10px;padding:8px 12px;font-size:13px;font-weight:600;cursor:pointer}
        .sec{background:#fff;color:#0f172a;border:1px solid #cbd5e1;border-radius:10px;padding:7px 11px;font-size:13px;cursor:pointer}
        .foot{padding:8px 16px;font-size:11px;color:#64748b;border-top:1px solid #f1f5f9;display:flex;justify-content:space-between;gap:8px}
        .chat{display:none;margin-top:10px}.chat.open{display:block}.chat form{display:flex;gap:6px}
        .chat input{flex:1;border:1px solid #cbd5e1;border-radius:10px;padding:7px 9px;font-size:13px}
        .ans{background:#f1f5f9;border-radius:10px;padding:8px 10px;margin-top:8px;font-size:13px;white-space:pre-line}
        a{color:#0f766e;cursor:pointer}
      </style><div id="box"></div>`;
    }
    return root.getElementById("box");
  }

  const pill = (text, onClick) => {
    box().innerHTML = `<button class="pill" id="p">${text}</button>`;
    if (onClick) box().querySelector("#p").addEventListener("click", onClick);
  };

  function showError(error) {
    pill("FinPilot · not connected", () => {
      box().innerHTML = `<div class="card"><div class="head"><div><div class="title">FinPilot is not connected</div><div class="sub">${esc(error)}</div></div><button class="x" id="x">×</button></div>
        <div class="body">Open the FinPilot popup (puzzle icon → FinPilot), log in, and make sure the platform is running.</div></div>`;
      box().querySelector("#x").addEventListener("click", () => showError(error));
    });
  }

  function showCard() {
    const v = verdict, d = D[v.decision];
    const m = v.market;
    box().innerHTML = `
      <div class="card">
        <div class="head" style="background:${d.bg};border-bottom:1px solid ${d.line}">
          <div><div class="title">${d.icon} ${esc(v.title_text)}</div>
            <div class="sub">${esc((product.title || "This item").slice(0, 70))} · <b>${money(product.price)}</b> · ${esc(v.category_name)}</div></div>
          <button class="x" id="min" title="Minimize">–</button>
        </div>
        <div class="body">
          ${v.reasonable_price ? `<div class="fair"><span>Reasonable price for you</span><b>up to ${money(Math.round(v.reasonable_price))}</b></div>`
            : v.no_room_this_month ? `<div class="fair"><span>No room in this month's ${esc(v.category_name)} budget</span><span class="sub">fresh month ${esc(v.next_month_starts)}</span></div>` : ""}
          <ul>${v.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
          ${v.risk_after != null ? `<div class="meter">Chance of overspending ${esc(v.category_name)} this month: ${pct(v.risk_before)} → <b>${pct(v.risk_after)}</b></div>
            <div class="bar"><div style="width:${Math.round(v.risk_after * 100)}%;background:${d.bar}"></div></div>` : ""}
          ${m ? `<div class="market">Similar items cost <b>${money(Math.round(m.low))}–${money(Math.round(m.high))}</b> (2023 prices)</div>` : ""}
          <div class="row">
            ${v.decision !== "buy" ? `<button class="main" id="postpone">Postpone</button>` : ""}
            <button class="sec" id="ask">Ask FinPilot</button>
            <button class="sec" id="dismiss">${v.decision === "buy" ? "OK" : "Buy anyway"}</button>
          </div>
          <div class="chat" id="chat"><form id="cf"><input id="q" placeholder="What if I wait until payday?" autocomplete="off"><button class="main">Ask</button></form><div id="answers"></div></div>
        </div>
        <div class="foot"><span>For ${esc(v.checked_for)} · family budget · prototype, not financial advice</span><a id="open">Open</a></div>
      </div>`;
    const $ = (s) => box().querySelector(s);
    $("#min").addEventListener("click", () => pill(`${d.icon} FinPilot · ${esc(v.title_text)}`, showCard));
    $("#dismiss").addEventListener("click", () => pill(`${d.icon} FinPilot`, showCard));
    $("#open").addEventListener("click", () => send({ type: "openPanel" }));
    $("#postpone")?.addEventListener("click", async () => {
      const r = await send({ type: "postpone", product: { ...product, category: v.category, decision: v.decision, probability: v.risk_after } });
      $("#postpone").textContent = r.ok ? `Postponed ✓ reminder ${r.data.remind_on}` : "Could not save";
      $("#postpone").disabled = true;
    });
    $("#ask").addEventListener("click", () => { $("#chat").classList.add("open"); $("#q").focus(); });
    $("#cf").addEventListener("submit", async (e) => {
      e.preventDefault();
      const q = $("#q").value.trim();
      if (!q) return;
      $("#q").value = "";
      const div = document.createElement("div");
      div.className = "ans"; div.textContent = "…";
      $("#answers").prepend(div);
      const r = await send({ type: "chat", message: q, context: { title: product.title, price: product.price, url: product.url, category: v.category } });
      div.textContent = r.ok ? r.data.reply : r.error;
    });
  }

  async function check(p) {
    product = p;
    pill("FinPilot · checking budget, usual prices and market…");
    const r = await send({ type: "check", product: { title: p.title, price: p.price, url: p.url } });
    if (!r.ok) return showError(r.error);
    verdict = r.data;
    if (verdict.decision === "buy") pill(`${D.buy.icon} FinPilot · Buy · fits your budget`, showCard);
    else showCard();
  }

  function scan() {
    const p = window.FinPilotDetect.detectProduct(document);
    const key = p ? `${location.href}|${p.price}` : null;
    if (!p || key === lastKey) return;
    lastKey = key;
    check(p);
  }

  function fromSelection(text) {
    const price = window.FinPilotDetect.parsePrice(text);
    if (!price) return null;
    const title = text.replace(/(US)?\$\s?\d[\d.,]*|\d[\d.,]*\s?(USD|dollars)/gi, " ").replace(/\s+/g, " ").trim();
    return { title: title.length >= 3 ? title.slice(0, 160) : document.title, price, url: location.href };
  }

  chrome.runtime.onMessage.addListener((msg, _s, sendResponse) => {
    if (msg.type === "getProduct") sendResponse({ product: window.FinPilotDetect.detectProduct(document), url: location.href, title: document.title });
    else if (msg.type === "checkSelection") { const p = fromSelection(msg.text); if (p) check(p); else pill("FinPilot · no price in the selection"); }
    else if (msg.type === "checkManual") check(msg.product);
    return false;
  });

  scan();
  setTimeout(scan, 1500);
  setTimeout(scan, 4000);
  let lastUrl = location.href;
  setInterval(() => { if (location.href !== lastUrl) { lastUrl = location.href; lastKey = null; setTimeout(scan, 1200); } }, 1000);
})();
