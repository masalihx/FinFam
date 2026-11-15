// Ask: one assistant for the panel and the on-page card.
import { answer } from "../lib/assistant.js";
import { $, $$, esc } from "../lib/ui.js";

const log = [];      // {who, text, meta} shown on screen (kept while the panel is open)
const history = [];  // Gemini conversation turns (text only)
const SUGGESTIONS = ["What bills are coming up?", "Can I buy concert tickets for $100?", "How much did we spend on dining?", "Where are we losing money?", "How are our goals?"];

export async function ask(el, app, params) {
  let context = null;
  try { context = params.get("about") ? JSON.parse(params.get("about")) : null; } catch { context = null; }
  el.innerHTML = `<div class="stack" style="padding-bottom:64px">
    <div><h1>Ask FinPilot</h1><p class="xs muted" style="margin:0">Numbers come from your family's data and our models. ${app.store.data.settings.gemini_key ? "Answers by Gemini." : "Offline mode — add a Gemini key in Settings for smarter answers."}</p></div>
    ${context ? `<div class="section small">About: <b>${esc(context.title || "this item")}</b> · $${esc(context.price)}</div>` : ""}
    <div class="chat" id="log" role="log" aria-live="polite"></div>
    <div class="chips" id="sugg">${(context ? ["What if I wait until next month?", "Is this a good price?"] : SUGGESTIONS).map((s) => `<button class="chip">${esc(s)}</button>`).join("")}</div>
  </div>
  <form class="composer" id="f"><input class="input" id="q" placeholder="Ask about your family's money…" autocomplete="off" aria-label="Message"><button class="btn primary">Send</button></form>`;
  const box = $("#log", el);
  const draw = () => {
    const fmt = (t) => esc(t).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>"); // Gemini sometimes marks bold with **
    box.innerHTML = log.map((m) => `<div class="msg ${m.who}">${fmt(m.text)}${m.meta ? `<div class="meta">${esc(m.meta)}</div>` : ""}</div>`).join("")
      || `<div class="msg bot">Hi ${esc(app.store.me.name)}! Ask about spending, upcoming bills, goals, or whether something is worth buying.</div>`;
    window.scrollTo(0, document.body.scrollHeight);
  };
  const send = async (text) => {
    log.push({ who: "me", text });
    log.push({ who: "bot", text: "…" });
    draw();
    try {
      const r = await answer(app, text, context, history);
      log[log.length - 1] = { who: "bot", text: r.reply, meta: `${r.by}${r.tools.length ? ` · used ${[...new Set(r.tools)].join(", ")}` : ""}` };
      history.push({ role: "user", parts: [{ text }] }, { role: "model", parts: [{ text: r.reply }] });
    } catch (e) { log[log.length - 1] = { who: "bot", text: e.message }; }
    draw();
  };
  draw();
  $$("#sugg .chip", el).forEach((b) => b.addEventListener("click", () => send(b.textContent)));
  $("#f", el).addEventListener("submit", (e) => { e.preventDefault(); const q = $("#q", el); if (q.value.trim()) { send(q.value.trim()); q.value = ""; } });
  $("#q", el).focus();
}
