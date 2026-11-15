// FinPilot ML engine in the browser: exact ports of the scikit-learn models trained in ml/.
// TF-IDF (word + char_wb, sublinear tf, l2) + logistic/ridge, and HistGradientBoosting trees.

// ------------------------------------------------------------------ text cleaning (port of ml/text_utils.py)

const WRAPPERS = new RegExp([
  "recurring card purchase(?: with pin)?",
  "recurring payment authorized on",
  "purchase authorized on",
  "debit card purchase",
  "card purchase(?: with pin)?(?! return)",
  "checkcard",
  "(?<=\\] )purchase(?! interest)",
  "\\bcard \\d{4}\\b",
  "\\bs\\d{9,}\\b",
  "#\\s?\\d+",
  "\\b\\d{1,2}[:/]\\d{2}[ap]?\\b",
].join("|"), "g");

export function normalize(text) {
  let low = String(text).toLowerCase();
  low = low.replace(WRAPPERS, " ");
  low = low.replace(/\d+/g, "0");
  return low.replace(/\s+/g, " ").trim();
}

export function withSign(amount, description) {
  return (amount < 0 ? "[debit] " : "[credit] ") + description;
}

// ------------------------------------------------------------------ TF-IDF

const WORD_RE = /[\p{L}\p{N}_]{2,}/gu;

function wordNgrams(doc, [lo, hi]) {
  const tokens = doc.match(WORD_RE) || [];
  const out = [];
  for (let n = lo; n <= hi; n++) for (let i = 0; i + n <= tokens.length; i++) out.push(tokens.slice(i, i + n).join(" "));
  return out;
}

function charWbNgrams(doc, [lo, hi]) {
  const text = doc.replace(/\s\s+/g, " ");
  const out = [];
  for (const raw of text.split(/\s+/).filter(Boolean)) {
    const w = " " + raw + " ";
    for (let n = lo; n <= hi; n++) {
      let offset = 0;
      out.push(w.slice(offset, offset + n));
      while (offset + n < w.length) { offset += 1; out.push(w.slice(offset, offset + n)); }
      if (offset === 0) break; // a short word is counted once
    }
  }
  return out;
}

class Vectorizer {
  constructor(spec, preprocess) {
    this.analyzer = spec.analyzer;
    this.range = spec.ngram_range;
    this.idf = spec.idf;
    this.index = new Map(spec.terms.map((t, i) => [t, i]));
    this.preprocess = preprocess;
  }
  transform(text) { // sparse vector as Map(index -> value), l2-normalized
    const doc = this.preprocess(text);
    const grams = this.analyzer === "word" ? wordNgrams(doc, this.range) : charWbNgrams(doc, this.range);
    const tf = new Map();
    for (const g of grams) { const i = this.index.get(g); if (i !== undefined) tf.set(i, (tf.get(i) || 0) + 1); }
    let norm = 0;
    for (const [i, c] of tf) { const v = (1 + Math.log(c)) * this.idf[i]; tf.set(i, v); norm += v * v; }
    norm = Math.sqrt(norm);
    if (norm > 0) for (const [i, v] of tf) tf.set(i, v / norm);
    return tf;
  }
}

class TextModel {
  constructor(spec, preprocess) {
    this.spec = spec;
    this.parts = spec.features.map((f) => new Vectorizer(f, preprocess));
    this.offsets = [];
    let o = 0;
    for (const f of spec.features) { this.offsets.push(o); o += f.terms.length; }
  }
  features(text) {
    const out = [];
    this.parts.forEach((p, k) => { for (const [i, v] of p.transform(text)) out.push([this.offsets[k] + i, v]); });
    return out;
  }
}

export class Classifier extends TextModel { // multinomial logistic regression
  scores(text) {
    const x = this.features(text);
    return this.spec.classes.map((_, c) => {
      const w = this.spec.coef[c];
      let s = this.spec.intercept[c];
      for (const [i, v] of x) s += w[i] * v;
      return s;
    });
  }
  predict(text) { return this.proba(text)[0].label; }
  proba(text) {
    const s = this.scores(text);
    const m = Math.max(...s);
    const e = s.map((v) => Math.exp(v - m));
    const z = e.reduce((a, b) => a + b, 0);
    return this.spec.classes.map((label, i) => ({ label, p: e[i] / z })).sort((a, b) => b.p - a.p);
  }
}

export class Regressor extends TextModel { // ridge regression on log(price)
  predict(text) {
    let s = this.spec.intercept;
    for (const [i, v] of this.features(text)) s += this.spec.coef[i] * v;
    return s;
  }
}

export const lowerPre = (t) => String(t).toLowerCase();

// ------------------------------------------------------------------ gradient-boosted trees

export class Trees {
  constructor(spec) {
    this.spec = spec;
    this.pos = spec.order.map((f) => spec.features.indexOf(f)); // internal column -> input feature index
  }
  raw(x) { // x: array in spec.features order
    const xt = this.spec.order.map((f, j) => {
      const v = x[this.pos[j]];
      const cats = this.spec.categorical_values[f];
      if (!cats) return v;
      const k = cats.indexOf(v);
      return k < 0 ? NaN : k;
    });
    let s = this.spec.baseline;
    for (const t of this.spec.trees) {
      let n = 0;
      while (!t.leaf[n]) {
        const v = xt[t.feature[n]];
        let left;
        if (v === null || v === undefined || Number.isNaN(v)) left = !!t.missing_left[n];
        else if (t.categorical[n]) {
          const bits = t.cat_bitsets[t.bitset[n]];
          const iv = v | 0;
          left = ((bits[iv >> 5] >>> (iv & 31)) & 1) === 1;
        } else left = v <= t.threshold[n];
        n = left ? t.left[n] : t.right[n];
      }
      s += t.value[n];
    }
    return s;
  }
  proba(x) { return 1 / (1 + Math.exp(-this.raw(x))); }
}

// ------------------------------------------------------------------ loading

export async function loadModels(base = "") {
  const get = async (name) => (await fetch(`${base}models/${name}.json`)).json();
  const [cat, price, intent, overspend, recurring] = await Promise.all(
    ["categorizer", "price", "intent", "overspend", "recurring"].map(get));
  return {
    categorizer: new Classifier(cat, normalize),
    price: new Regressor(price, lowerPre),
    priceSpec: price,
    intent: new Classifier(intent, lowerPre),
    overspend: new Trees(overspend),
    overspendSpec: overspend,
    recurring: new Trees(recurring),
    recurringSpec: recurring,
    needs: new Set(cat.needs),
    wants: new Set(cat.wants),
    tests: { categorizer: cat.tests, price: price.tests, intent: intent.tests, overspend: overspend.tests, recurring: recurring.tests },
  };
}
