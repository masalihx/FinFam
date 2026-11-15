// Small date helpers on "YYYY-MM-DD" strings (no time zones involved).

export const parse = (s) => { const [y, m, d] = s.split("-").map(Number); return { y, m, d }; };
export const fmt = (y, m, d) => `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
export const monthIndex = (s) => { const { y, m } = parse(s); return y * 12 + (m - 1); };
export const monthStr = (mi) => `${Math.floor(mi / 12)}-${String((mi % 12) + 1).padStart(2, "0")}`;
export const daysInMonth = (y, m) => new Date(Date.UTC(y, m, 0)).getUTCDate();
export const dayOf = (s) => parse(s).d;
export const toUTC = (s) => { const { y, m, d } = parse(s); return Date.UTC(y, m - 1, d); };
export const daysBetween = (a, b) => Math.round((toUTC(b) - toUTC(a)) / 86400000); // b - a
export const addDays = (s, n) => new Date(toUTC(s) + n * 86400000).toISOString().slice(0, 10);

// pandas DateOffset(months=k): same day, clamped to the end of the month.
export function addMonths(s, k) {
  const { y, m, d } = parse(s);
  const mi = y * 12 + (m - 1) + k;
  const ny = Math.floor(mi / 12), nm = (mi % 12) + 1;
  return fmt(ny, nm, Math.min(d, daysInMonth(ny, nm)));
}
const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
export const monthName = (mi) => MONTH_NAMES[((mi % 12) + 12) % 12];
export const firstOfMonth = (mi) => `${monthStr(mi)}-01`;

export function todayStr() {
  const t = new Date();
  return fmt(t.getFullYear(), t.getMonth() + 1, t.getDate());
}
