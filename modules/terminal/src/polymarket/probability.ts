/**
 * Turning a probability into something an operator reads, in one place.
 *
 * **The scale is 0..1 everywhere behind this file**, and this is where — and only where —
 * it becomes a percentage on screen. Written once because the mistake it guards against is
 * silent: 0,62 read as 62 is wrong by two orders of magnitude and throws nothing on the
 * way, so a second place that multiplied by a hundred would be a second place that could
 * forget to (specs/terminal-polymarket, "Lista pokazuje wydarzenie, nie pojedynczą
 * monetę").
 *
 * Everything here answers `null` rather than a zero or a dash of its own, so a view can
 * decide how absence looks and cannot mistake it for a value.
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
