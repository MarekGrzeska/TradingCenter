/**
 * Where — and only where — a 0..1 scale becomes a percentage on screen: 0,62 read as 62 is wrong by two orders of
 * magnitude and throws nothing, so a second place that multiplied would be a second place that could forget to.
 */

/** How stale a price has to be before the view says so, rather than showing it as now.
 *
 *  Twice the module's own sampling tick (60s), so one skipped sample is not an alarm and a
 *  collector that has stopped is. */
export const STALE_AFTER_MS = 120_000;

/** `0.62` → `"62.0%"`. The one multiplication by a hundred in this tab. */
export function formatProbability(price: number | null): string | null {
  if (price === null) return null;
  return `${(price * 100).toFixed(1)}%`;
}

/** `0.021` → `"+2.1 pp"`. **Points, not percent**, and the unit is in the string because
 *  the two are confused exactly here: a move from 0,60 to 0,62 is two points and is also
 *  a rise of 3,3%, and a bare "+2.1%" would be the second thing said with the first
 *  thing's number. */
export function formatChange(change: number | null): string | null {
  if (change === null) return null;
  const points = change * 100;
  const sign = points > 0 ? "+" : points < 0 ? "−" : "";
  return `${sign}${Math.abs(points).toFixed(1)} pp`;
}

export type ChangeDirection = "up" | "down" | "flat";

export function directionOf(change: number | null): ChangeDirection | null {
  if (change === null) return null;
  if (change > 0) return "up";
  if (change < 0) return "down";
  return "flat";
}

/** Whether a price is old enough that showing it as current would be a claim.
 *
 *  A price with no moment is stale by definition: it cannot be dated, so it cannot be
 *  vouched for. */
export function isStale(priceAt: Date | null, now: Date = new Date()): boolean {
  if (priceAt === null) return true;
  return now.getTime() - priceAt.getTime() > STALE_AFTER_MS;
}

/** `"4 min ago"`, for the moment beside a price. Coarse on purpose: the tick is a minute,
 *  so seconds would be noise that changes on every render. */
export function formatAge(priceAt: Date | null, now: Date = new Date()): string | null {
  if (priceAt === null) return null;
  const seconds = Math.max(0, Math.round((now.getTime() - priceAt.getTime()) / 1000));
  if (seconds < 90) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}

/** The five bands a probability's colour comes from, repeating what length says because a column of bars is
 *  scanned rather than read. **Stepped by the validator, not by eye** — the first pair failed ΔE 8.3 against 15. */
export interface ProbabilityBand {
  /** Inclusive lower edge, on 0..1. */
  from: number;
  fill: string;
  /** What this band means, for the bar's own tooltip. */
  reading: string;
}

export const BANDS: ProbabilityBand[] = [
  { from: 0, fill: "#c93a3a", reading: "unlikely" },
  { from: 0.2, fill: "#ef7a2e", reading: "leaning against" },
  { from: 0.4, fill: "#f5e05a", reading: "close to even" },
  { from: 0.6, fill: "#6ec96e", reading: "leaning for" },
  { from: 0.8, fill: "#12855f", reading: "likely" },
];

/** The band a probability falls in. `null` for no price — a band would be a colour standing
 *  for a value nobody has. */
export function bandFor(price: number | null): ProbabilityBand | null {
  if (price === null) return null;
  const clamped = Math.max(0, Math.min(1, price));
  // Walked from the top so an exact edge belongs to the band it opens.
  return [...BANDS].reverse().find((band) => clamped >= band.from) ?? BANDS[0];
}
