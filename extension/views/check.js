// Check a purchase: the same verdict the on-page card shows.
import { checkPurchase } from "../lib/verdict.js";
import { $, $$, BAR, DECISION, busy, esc, formData, money, pct, shortDate, toast } from "../lib/ui.js";

const EXAMPLES = [
  ["Concert tickets", 100, "https://www.ticketmaster.com/event/1"],
  ["Sony WH-1000XM5 Wireless Noise Canceling Headphones", 348, "https://www.amazon.com/dp/B09XS7JWHH"],
  ["TI-84 Plus graphing calculator for school", 129, "https://www.amazon.com/dp/1"],
  ["Stainless steel water bottle 32 oz", 24, "https://www.amazon.com/dp/2"],
];

export function verdictHTML(r) {
  const [tone] = DECISION[r.decision];
  const risk = r.risk_after != null ? `
    <p class="xs muted" style="margin:12px 0 0">Chance of overspending ${esc(r.category_name)} this month: ${pct(r.risk_before)} → <b>${pct(r.risk_after)}</b></p>
    <div class="bar" aria-hidden="true"><span style="width:${Math.round(r.risk_after * 100)}%;background:${BAR[r.risk_after >= 0.75 ? "red" : r.risk_after >= 0.44 ? "yellow" : "green"]}"></span></div>
    ${r.budget ? `<p class="xs muted" style="margin:4px 0 0">Spent ${money(r.spent_this_month)} of ${money(r.budget)} so far</p>` : ""}` : "";
  const fair = r.reasonable_price ? `<div class="fair"><span>Reasonable price for you</span><b>up to ${money(r.reasonable_price)}</b></div>`
    : r.no_room_this_month ? `<div class="fair"><span>No room in this month's ${esc(r.category_name)} budget</span><span class="xs muted">fresh month ${shortDate(r.next_month_starts)}</span></div>` : "";
  return `<article class="verdict ${r.decision}" aria-live="polite">
    <div class="head"><div class="decision"><span class="tag ${tone}" style="vertical-align:middle">${r.decision === "buy" ? "✓" : r.decision === "think" ? "?" : "✕"}</span> ${esc(r.title_text)}</div>
      <div class="small muted">${esc(r.title || "This item")} · <b>${money(r.price, 2)}</b> · ${esc(r.category_name)} (${esc(r.kind)})</div></div>
    <div class="body">${fair}<ul>${r.reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>${risk}
      ${r.market ? `<p class="xs muted" style="margin:10px 0 0">Similar items cost <b>${money(r.market.low)}–${money(r.market.high)}</b> (2023 prices; ${esc(r.market.source)})</p>` : ""}
    </div></article>`;
}

export async function check(el, app, params) {
  el.innerHTML = `<div class="stack">
    <div><h1>Is it worth it?</h1><p class="muted small" style="margin:0">Checks the family budget, your usual prices and market prices. The extension does this on any product page.</p></div>
    <form class="section stack" id="f">
      <label class="field">Product<input class="input" name="title" required value="${esc(params.get("title") || "")}" placeholder="Concert tickets"></label>
      <div class="grid2"><label class="field">Price, $<input class="input" name="price" type="number" min="1" step="0.01" required value="${esc(params.get("price") || "")}"></label>
        <label class="field">Store link<input class="input" name="url" value="${esc(params.get("url") || "")}" placeholder="optional"></label></div>
      <button class="btn primary block">Check</button>
      <div class="chips" aria-label="Examples">${EXAMPLES.map((e, i) => `<button type="button" class="chip" data-ex="${i}">${esc(e[0].split(" ").slice(0, 3).join(" "))} · $${e[1]}</button>`).join("")}</div>
    </form>
    <div id="out"></div></div>`;
  const form = $("#f", el);
  $$("[data-ex]", el).forEach((b) => b.addEventListener("click", () => {
    const [t, p, u] = EXAMPLES[b.dataset.ex];
    form.elements.namedItem("title").value = t; form.elements.namedItem("price").value = p; form.elements.namedItem("url").value = u;
    form.requestSubmit();
  }));
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const f = formData(form), out = $("#out", el);
    out.innerHTML = `<div class="skeleton" style="height:160px" role="status" aria-label="Checking"></div>`;
    busy(e.submitter || form.querySelector("button"), async () => {
      try {
        const r = await checkPurchase(app, f);
        out.innerHTML = verdictHTML(r) + `<div style="display:flex;gap:8px;margin-top:12px">${r.decision !== "buy" ? `<button class="btn primary" id="pp">Postpone</button>` : ""}<a class="btn ghost" href="#ask?about=${encodeURIComponent(JSON.stringify({ title: r.title, price: r.price, url: r.url, category: r.category }))}">Ask FinPilot</a></div>`;
        $("#pp", out)?.addEventListener("click", async () => {
          const remind = await app.store.postpone({ title: r.title || "Item", price: r.price, url: r.url, category: r.category, decision: r.decision, probability: r.risk_after });
          toast(`Postponed. Reminder on ${shortDate(remind)}.`);
        });
      } catch (err) { out.innerHTML = `<div class="section" role="alert">${esc(err.message)}</div>`; }
    });
  });
  if (params.get("price")) form.requestSubmit();
}
