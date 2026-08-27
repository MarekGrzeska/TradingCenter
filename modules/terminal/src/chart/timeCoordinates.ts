import type { ITimeScaleApi, Logical, Time } from "lightweight-charts";

/**
 * The x coordinate for an arbitrary instant, not only one the chart has a bar at: the library maps *bars*, and
 * a window ending at 16:30 on an hourly chart has none. Falls back to the nearest; `null` means no bars at all.
 */
export function timeToX(timeScale: ITimeScaleApi<Time>, time: Time): number | null {
  const exact = timeScale.timeToCoordinate(time);
  if (exact !== null) return exact;

  const nearest = timeScale.timeToIndex(time, true);
  if (nearest === null) return null;
  return timeScale.logicalToCoordinate(nearest as unknown as Logical);
}
