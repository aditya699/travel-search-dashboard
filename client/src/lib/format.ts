const inr = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});
const count = new Intl.NumberFormat("en-IN");

/** ₹4,599 with Indian digit grouping (₹1,00,000). */
export const rupees = (value: number | null | undefined) => (value == null ? "-" : inr.format(value));

export const number = (value: number | null | undefined) => (value == null ? "-" : count.format(value));

/** "2026-11-25" -> "Wed 25 Nov". Parsed as a calendar date, never shifted by time zone. */
export function day(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, d ?? 1));
  return date.toLocaleDateString("en-IN", {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
}

/** "2026-11-25" -> "25 Nov". */
export function shortDay(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, d ?? 1));
  return date.toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: "UTC" });
}

export const percent = (value: number | null | undefined, digits = 1) =>
  value == null ? "-" : `${value.toFixed(digits)}%`;
