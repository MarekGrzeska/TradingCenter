import { todayInWarsaw, warsawMidnightEpochSeconds } from "../../ui/formatTime";

/**
 * The Agents cost tab's date range, as `<input type="date">` trades in it — a
 * `YYYY-MM-DD` string with no timezone of its own — converted to the epoch-second
 * bounds `GET /usage` actually takes. Kept apart from `useUsage.ts` and the view: the
 * only thing worth a unit test here is the arithmetic, not a render.
 */

export interface DateRangeInputs {
  from: string;
  to: string;
}

/** A pure calendar-day step on the `YYYY-MM-DD` string — independent of any
 *  timezone, since the string itself carries none. `Date.UTC` is only how month and
 *  year boundaries get carried; nothing here is a real UTC instant. */
function addCalendarDays(dateInput: string, days: number): string {
  const [year, month, day] = dateInput.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day + days)).toISOString().slice(0, 10);
}

/** Exported on its own: the exclusive-`to` boundary below is the one piece of this
 *  file most worth a test by itself, since getting it wrong either drops the picked
 *  day's own usage or leaks one extra day in. */
export function nextCalendarDay(dateInput: string): string {
  return addCalendarDays(dateInput, 1);
}

/** The last seven Warsaw calendar days, `to` included — enough to answer "did
 *  anything change lately" without asking the operator to pick a range before they
 *  have seen anything at all. */
export function defaultDateRangeInputs(): DateRangeInputs {
  const to = todayInWarsaw();
  return { from: addCalendarDays(to, -6), to };
}

/** `to` is a calendar day, but the module's own `to` is an exclusive instant
 *  (`agent/store.py`: `u.created_at < $3`) — resolved to the *following* day's own
 *  Warsaw midnight so the picked day stays entirely inside the range. */
export function toUsageRange(inputs: DateRangeInputs): { from: number; to: number } {
  return {
    from: warsawMidnightEpochSeconds(inputs.from),
    to: warsawMidnightEpochSeconds(nextCalendarDay(inputs.to)),
  };
}
