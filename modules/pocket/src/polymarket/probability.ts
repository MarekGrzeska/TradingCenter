/**
 * Where — and only where — a 0..1 scale becomes a percentage on screen: 0,62 read as 62 is wrong by two
 * orders of magnitude and throws nothing, so a second place that multiplied could forget to.
 */

/** How stale a price has to be before the screen says so rather than showing it as now. Twice the
 *  archive's own sampling tick (60s), so one skipped sample is not an alarm and a stopped collector is. */
export const STALE_AFTER_MS = 120_000;

/** `0.62` to `"62%"`. Whole points, because this is read at arm's length on a phone; the tenth of a
 *  point the terminal shows is detail nobody scrolling a list acts on. */
export function formatProbability(price: number | null): string {
  if (price === null) return "—";
  return `${Math.round(price * 100)}%`;
}

/** `0.021` to `"+2.1 pp"`. **Points, not percent**, and the unit is in the string because the two are
 *  confused exactly here: 0,60 to 0,62 is two points and is also a rise of 3,3%. */
export function formatChange(change: number | null): string {
  if (change === null) return "—";
  const points = change * 100;
  const sign = points > 0 ? "+" : points < 0 ? "-" : "";
  return `${sign}${Math.abs(points).toFixed(1)} pp`;
}

export type Direction = "up" | "down" | "flat" | "none";

export function directionOf(change: number | null): Direction {
  if (change === null) return "none";
  if (change > 0) return "up";
  if (change < 0) return "down";
  return "flat";
}

/** Whether a price is old enough that showing it as current would be a claim. A price with no moment
 *  is stale by definition: it cannot be dated, so it cannot be vouched for. */
export function isStale(priceAt: Date | null, now: Date = new Date()): boolean {
  if (priceAt === null) return true;
  return now.getTime() - priceAt.getTime() > STALE_AFTER_MS;
}

/** `"4 min ago"`, for the moment beside a price. Coarse on purpose: the tick is a minute, so seconds
 *  would be noise that changes on every render. */
export function formatAge(priceAt: Date | null, now: Date = new Date()): string {
  if (priceAt === null) return "never";
  const seconds = Math.max(0, Math.round((now.getTime() - priceAt.getTime()) / 1000));
  if (seconds < 90) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}

/** The five bands a probability's colour comes from, repeating what the bar's length says because a
 *  column of bars is scanned rather than read. */
export interface Band {
  /** Inclusive lower edge, on 0..1. */
  from: number;
  fill: string;
  /** What this band means, for the bar's own label. */
  reading: string;
}

export const BANDS: Band[] = [
  { from: 0, fill: "#c93a3a", reading: "unlikely" },
  { from: 0.2, fill: "#ef7a2e", reading: "leaning against" },
  { from: 0.4, fill: "#f5e05a", reading: "close to even" },
  { from: 0.6, fill: "#6ec96e", reading: "leaning for" },
  { from: 0.8, fill: "#12855f", reading: "likely" },
];

/** The band a probability falls in, or `null` for no price — a band would be a colour standing for a
 *  value nobody has. */
export function bandFor(price: number | null): Band | null {
  if (price === null) return null;
  const clamped = Math.max(0, Math.min(1, price));
  // Walked from the top so an exact edge belongs to the band it opens.
  return [...BANDS].reverse().find((band) => clamped >= band.from) ?? BANDS[0];
}
