import type { ITimeScaleApi, Logical, Time } from "lightweight-charts";

/**
 * The x coordinate for an arbitrary instant — not only for one the chart has a bar at.
 *
 * `timeToCoordinate` answers `null` "if no time found on time scale": it maps *bars*, not
 * moments. Anything computed on the chart's own series lands on a bar and never notices.
 * The shapes that do not are exactly the ones that read a different series than the one
 * being drawn — a `session_range` window ending at 16:30 on an hourly chart, a previous-day
 * pivot whose close moment is a midnight the venue was shut through. Those moments sit
 * inside the loaded range and still have no bar of their own, and letting `null` through is
 * how a zone or a ray disappears with nothing failing anywhere.
 *
 * Falls back to the nearest bar, which is the honest answer at this chart's resolution: an
 * hourly chart cannot draw 16:30 anywhere but beside 16:00. `null` is kept for the one case
 * it really means — no bars at all to be near.
 */
export function timeToX(timeScale: ITimeScaleApi<Time>, time: Time): number | null {
  const exact = timeScale.timeToCoordinate(time);
  if (exact !== null) return exact;

  const nearest = timeScale.timeToIndex(time, true);
  if (nearest === null) return null;
  return timeScale.logicalToCoordinate(nearest as unknown as Logical);
}
