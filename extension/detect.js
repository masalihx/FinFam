// Finds the product name and price on a shop page.
// Order: schema.org Product data (most shops) -> meta tags -> Amazon layout -> microdata.
(function () {
  const CURRENCY_SIGNS = { "$": "USD", "€": "EUR", "£": "GBP", "₸": "KZT", "₽": "RUB", "¥": "JPY" };

  function parsePrice(text) {
    if (text == null) return null;
    if (typeof text === "number") return text > 0 ? text : null;
    let s = String(text).replace(/\s| /g, "");
    const m = s.match(/\d[\d.,]*/);
    if (!m) return null;
    s = m[0];
    const lastComma = s.lastIndexOf(","), lastDot = s.lastIndexOf(".");
    if (lastComma > lastDot) {
      // "1.299,99" or "1299,99": comma is the decimal mark if 1-2 digits follow it
      s = /,\d{1,2}$/.test(s) ? s.replace(/\./g, "").replace(",", ".") : s.replace(/,/g, "");
    } else {
      s = s.replace(/,/g, "");
    }
    const v = parseFloat(s);
    return Number.isFinite(v) && v > 0 ? v : null;
  }

  function currencyOf(text) {
    for (const [sign, code] of Object.entries(CURRENCY_SIGNS)) if (String(text || "").includes(sign)) return code;
    return null;
  }

  function* jsonLdNodes(doc) {
    for (const el of doc.querySelectorAll('script[type="application/ld+json"]')) {
      let data;
      try { data = JSON.parse(el.textContent); } catch { continue; }
      const stack = [data];
      while (stack.length) {
        const node = stack.pop();
        if (!node || typeof node !== "object") continue;
        if (Array.isArray(node)) { stack.push(...node); continue; }
        yield node;
        if (node["@graph"]) stack.push(node["@graph"]);
      }
    }
  }

  function fromJsonLd(doc) {
    for (const node of jsonLdNodes(doc)) {
      const types = [].concat(node["@type"] || []);
      if (!types.includes("Product")) continue;
      const offers = [].concat(node.offers || []);
      for (const o of offers) {
        const price = parsePrice(o.price ?? o.lowPrice ?? o.priceSpecification?.price);
        if (price) return { title: node.name, price, currency: o.priceCurrency || null, source: "schema.org" };
      }
    }
    return null;
  }

  function meta(doc, names) {
    for (const n of names) {
      const el = doc.querySelector(`meta[property="${n}"], meta[name="${n}"], meta[itemprop="${n}"]`);
      if (el?.content) return el.content;
    }
    return null;
  }

  function fromMeta(doc) {
    const price = parsePrice(meta(doc, ["product:price:amount", "og:price:amount", "price"]));
    if (!price) return null;
    return {
      title: meta(doc, ["og:title", "twitter:title"]) || doc.title,
      price,
      currency: meta(doc, ["product:price:currency", "og:price:currency", "priceCurrency"]),
      source: "meta tags",
    };
  }

  function fromAmazon(doc) {
    const title = doc.querySelector("#productTitle")?.textContent?.trim();
    if (!title) return null;
    const priceEl = doc.querySelector(
      "#corePrice_feature_div .a-price .a-offscreen, #corePriceDisplay_desktop_feature_div .a-price .a-offscreen, " +
        "#apex_desktop .a-price .a-offscreen, #priceblock_ourprice, #priceblock_dealprice, .a-price .a-offscreen"
    );
    const text = priceEl?.textContent;
    const price = parsePrice(text);
    return price ? { title, price, currency: currencyOf(text) || "USD", source: "Amazon page" } : null;
  }

  function fromMicrodata(doc) {
    const priceEl = doc.querySelector('[itemprop="price"]');
    if (!priceEl) return null;
    const price = parsePrice(priceEl.getAttribute("content") || priceEl.textContent);
    if (!price) return null;
    const title = doc.querySelector('[itemprop="name"]')?.textContent?.trim() || doc.title;
    return { title, price, currency: currencyOf(priceEl.textContent), source: "microdata" };
  }

  function detectProduct(doc = document) {
    for (const finder of [fromJsonLd, fromMeta, fromAmazon, fromMicrodata]) {
      try {
        const found = finder(doc);
        if (found && found.price) {
          return { ...found, title: (found.title || doc.title || "").trim().slice(0, 200), url: location.href };
        }
      } catch (e) {
        /* try the next method */
      }
    }
    return null;
  }

  window.FinPilotDetect = { detectProduct, parsePrice, currencyOf };
})();
