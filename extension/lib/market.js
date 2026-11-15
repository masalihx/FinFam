// Market price from our database: the k most similar Amazon products (2023) by title, port of ml/train_price_knn.py.
// TF-IDF (sublinear tf, l2) cosine similarity; similarity-weighted median and 25-75% range of their prices.
const TOKEN = /[\p{L}\p{N}]{2,}|\p{N}+/gu;
const clean = (t) => String(t).toLowerCase().replace(/\s+/g, " ").slice(0, 120);

export class MarketIndex {
  constructor(spec) {
    this.k = spec.k;
    this.prices = spec.prices;
    this.titles = spec.titles;
    this.idf = spec.idf;
    this.vocab = new Map(spec.terms.map((t, i) => [t, i]));
    this.postings = new Map(); // term -> [[doc, weight], ...]
    spec.titles.forEach((title, d) => {
      for (const [term, w] of this.vector(title)) {
        if (!this.postings.has(term)) this.postings.set(term, []);
        this.postings.get(term).push([d, w]);
      }
    });
  }

  vector(text) {
    const tf = new Map();
    for (const tok of clean(text).match(TOKEN) || []) { const i = this.vocab.get(tok); if (i !== undefined) tf.set(i, (tf.get(i) || 0) + 1); }
    let norm = 0;
    for (const [i, c] of tf) { const v = (1 + Math.log(c)) * this.idf[i]; tf.set(i, v); norm += v * v; }
    norm = Math.sqrt(norm);
    for (const [i, v] of tf) tf.set(i, v / norm);
    return tf;
  }

  // {median, low, high, similar: [{title, price}], count} or null when nothing is similar.
  lookup(title) {
    const scores = new Map();
    for (const [term, qw] of this.vector(title)) for (const [d, w] of this.postings.get(term) || []) scores.set(d, (scores.get(d) || 0) + qw * w);
    if (!scores.size) return null;
    const top = [...scores].sort((a, b) => b[1] - a[1]).slice(0, this.k);
    const byPrice = top.map(([d, w]) => ({ p: this.prices[d], w })).sort((a, b) => a.p - b.p);
    const total = byPrice.reduce((s, x) => s + x.w, 0);
    let cum = 0;
    const cw = byPrice.map((x) => (cum += x.w) / total);
    const at = (q) => byPrice[Math.min(byPrice.length - 1, cw.findIndex((c) => c >= q - 1e-12))].p;
    return { median: at(0.5), low: at(0.25), high: at(0.75), count: top.length,
      similar: top.slice(0, 3).map(([d]) => ({ title: this.titles[d], price: this.prices[d] })) };
  }
}
