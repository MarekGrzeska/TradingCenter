import type { Resolution } from "../data/types";

/** Compact labels for a resolution — cramming several archived intervals
 *  into one column, or one row of toggle buttons, the way the proposal
 *  itself writes them: `1m · 5m · 1h · 1D`. */
export const RESOLUTION_ABBR: Record<Resolution, string> = {
  MINUTE: "1m",
  MINUTE_5: "5m",
  MINUTE_15: "15m",
  MINUTE_30: "30m",
  HOUR: "1h",
  HOUR_4: "4h",
  DAY: "1D",
  WEEK: "1W",
};
