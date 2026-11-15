// Gemini API (free tier). Used to explain, chat and read files, and for one price opinion.
// It never computes the family's numbers: our models do (see finance.js, verdict.js).
export const DEFAULT_MODEL = "gemini-3.5-flash";
const URL = (model) => `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`;

export class GeminiError extends Error {}

export async function generate(settings, body, timeoutMs = 60000) {
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
  if (!res.ok) throw new GeminiError(`Gemini error ${res.status}: ${data.error?.message?.slice(0, 160) || "unknown"}`);
  return data;
}

export const textOf = (data) => (data.candidates?.[0]?.content?.parts || []).filter((p) => p.text).map((p) => p.text).join("");

export async function askJSON(settings, parts, timeoutMs) {
  const data = await generate(settings, { contents: [{ role: "user", parts }], generationConfig: { responseMimeType: "application/json", temperature: 0 } }, timeoutMs);
  try { return JSON.parse(textOf(data)); } catch { throw new GeminiError("Gemini gave an answer FinPilot could not read. Try again."); }
}

// One price opinion, in the same terms as our training data (US Amazon prices, 2023).
export async function estimatePrice(settings, title, hint) {
  const v = await askJSON(settings, [{ text: `Estimate the typical US Amazon price in 2023 (USD) for this product. Answer only with a JSON number.\n\n[${hint}] ${title.slice(0, 200)}` }], 20000);
  const n = typeof v === "number" ? v : Number(Object.values(v || {})[0]);
  if (!(n > 0)) throw new GeminiError("No price from Gemini.");
  return n;
}
