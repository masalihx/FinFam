// Gemini API (free tier). Used to explain, chat and read files, and for one price opinion.
// It never computes the family's numbers: our models do (see finance.js, verdict.js).
export const DEFAULT_MODEL = "gemini-3.5-flash-lite"; // lite models have a larger free daily quota
const URL = (model) => `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`;

export class GeminiError extends Error {}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Free tier allows a few requests per minute: on 429 wait and try again (twice).
export async function generate(settings, body, timeoutMs = 60000) {
  for (let attempt = 0; ; attempt++) {
    try { return await generateOnce(settings, body, timeoutMs); } catch (e) {
      if (!(e instanceof GeminiError) || !e.message.includes("429") || e.daily || attempt >= 2) throw e;
      await sleep(10000 * (attempt + 1));
    }
  }
}

async function generateOnce(settings, body, timeoutMs) {
  if (!settings?.gemini_key) throw new GeminiError("Add your Gemini API key in More → Settings.");
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  let res;
  try {
    res = await fetch(URL(settings.gemini_model || DEFAULT_MODEL), {
      method: "POST", signal: ctrl.signal,
      headers: { "Content-Type": "application/json", "x-goog-api-key": settings.gemini_key },
      body: JSON.stringify(body),
    });
  } catch (e) {
    throw new GeminiError(e.name === "AbortError" ? "Gemini took too long to answer." : "Cannot reach Gemini. Check the internet connection.");
  } finally { clearTimeout(timer); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const daily = JSON.stringify(data.error?.details || "").includes("PerDay");
    const err = new GeminiError(daily
      ? `Gemini error 429: the free daily limit for ${settings.gemini_model || DEFAULT_MODEL} is used up. Try again tomorrow or pick another model in Settings; FinPilot's own models still work.`
      : `Gemini error ${res.status}: ${data.error?.message?.slice(0, 160) || "unknown"}`);
    err.daily = daily;
    throw err;
  }
  return data;
}

export const textOf = (data) => (data.candidates?.[0]?.content?.parts || []).filter((p) => p.text).map((p) => p.text).join("");

export async function askJSON(settings, parts, timeoutMs) {
  const data = await generate(settings, { contents: [{ role: "user", parts }], generationConfig: { responseMimeType: "application/json", temperature: 0 } }, timeoutMs);
  try { return JSON.parse(textOf(data)); } catch { throw new GeminiError("Gemini gave an answer FinPilot could not read. Try again."); }
}

const EXTRACT_PROMPT = (today) =>
  "You read personal finance documents: store receipts, bank or card statements, or spreadsheets of expenses. " +
  `Extract every money movement as a JSON object with keys: date (YYYY-MM-DD; use ${today} if missing), ` +
  "description (merchant or payee, short), amount (number; NEGATIVE for money spent, POSITIVE for money received), " +
  "items (for a receipt: up to 5 main item names, otherwise empty list). For a single receipt return one row with the TOTAL paid. " +
  'Ignore running balances and subtotals. Answer only with a JSON object: {"document_type": "receipt|statement|spreadsheet|other", "rows": [...]}.';

const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"];

const toBase64 = (buf) => {
  let s = "";
  const bytes = new Uint8Array(buf);
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(s);
};

// Rows found in an uploaded file: photo of a receipt, PDF statement or CSV table.
export async function extractTransactions(settings, file, today) {
  const name = file.name.toLowerCase();
  let parts;
  if (name.endsWith(".csv") || file.type === "text/csv") {
    const text = (await file.text()).split("\n").slice(0, 400).join("\n");
    parts = [{ text: EXTRACT_PROMPT(today) }, { text: `Spreadsheet '${file.name}':\n${text}` }];
  } else if (name.endsWith(".xlsx") || name.endsWith(".xls")) {
    throw new GeminiError("Save the Excel file as CSV (File → Save As → CSV) and upload that.");
  } else if (IMAGE_TYPES.includes(file.type) || file.type === "application/pdf" || name.endsWith(".pdf")) {
    const mime = name.endsWith(".pdf") ? "application/pdf" : file.type;
    parts = [{ text: EXTRACT_PROMPT(today) }, { inline_data: { mime_type: mime, data: toBase64(await file.arrayBuffer()) } }];
  } else {
    throw new GeminiError("Upload a photo (JPG, PNG, WEBP, HEIC), a PDF, or a CSV table.");
  }
  if (file.size > 15 * 1024 * 1024) throw new GeminiError("File is larger than 15 MB.");
  const out = await askJSON(settings, parts, 120000);
  const rows = (out.rows || []).map((r) => ({
    date: /^\d{4}-\d{2}-\d{2}$/.test(r.date) ? r.date : today, description: String(r.description || "Unknown").slice(0, 120),
    amount: Math.round(Number(r.amount) * 100) / 100, items: (r.items || []).map(String).slice(0, 5),
  })).filter((r) => Number.isFinite(r.amount) && r.amount !== 0);
  return { document_type: out.document_type || "other", rows };
}

// One price opinion, in the same terms as our training data (US Amazon prices, 2023).
export async function estimatePrice(settings, title, hint) {
  const v = await askJSON(settings, [{ text: `Estimate the typical US Amazon price in 2023 (USD) for this product. Answer only with a JSON number.\n\n[${hint}] ${title.slice(0, 200)}` }], 20000);
  const n = typeof v === "number" ? v : Number(Object.values(v || {})[0]);
  if (!(n > 0)) throw new GeminiError("No price from Gemini.");
  return n;
}
