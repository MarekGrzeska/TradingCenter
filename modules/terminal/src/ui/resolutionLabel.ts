import type { Resolution } from "../data/types";

/** The terminal's one spelling for every resolution — the wire's own names never reach the screen. Shared by the chart's
 *  picker, Instruments, the wizard and Data History, so the same interval reads the same everywhere. */
export const RESOLUTION_LABEL: Record<Resolution, string> = {
  MINUTE: "m1",
  MINUTE_5: "m5",
  MINUTE_15: "m15",
  MINUTE_30: "m30",
  HOUR: "h1",
  HOUR_4: "h4",
  DAY: "day",
  WEEK: "week",
};
