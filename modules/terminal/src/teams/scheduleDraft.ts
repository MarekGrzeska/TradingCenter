import type {
  Recurrence,
  RecurrenceKind,
  RevisionMode,
  Schedule,
  ScheduleDraft,
  TriggerComparison,
  TriggerDraft,
} from "./teamsApi";

/** A schedule pinned to `revisionId` — the default a fresh form opens on, mirroring
 *  specs/teams-schedules' own default ("Domyślnie MUST to być rewizja przypięta") — and
 *  opened on a rhythm rather than an expression, which is what the wizard is for
 *  (specs/terminal-teams-schedules, "Harmonogram układa się rytmem i godziną"). */
export function emptyScheduleDraft(revisionId: number | null): ScheduleDraft {
  return {
    revisionMode: "pinned",
    pinnedRevisionId: revisionId,
    recurrence: recurrenceOfKind("daily", null),
    cronExpression: null,
  };
}

/** An existing schedule as something the form can edit. A schedule the module could not
 *  describe as a rhythm opens on its expression instead — and MUST come back out of the
 *  form unchanged (specs/terminal-teams-schedules, "Rytm spoza kreatora"). */
export function draftFromSchedule(schedule: Schedule): ScheduleDraft {
  return {
    revisionMode: schedule.revisionMode,
    pinnedRevisionId: schedule.pinnedRevisionId,
    recurrence: schedule.recurrence,
    cronExpression: schedule.recurrence === null ? schedule.cronExpression : null,
  };
}

export const RECURRENCE_KINDS: readonly RecurrenceKind[] = [
  "every_minutes",
  "hourly",
  "daily",
  "weekly",
  "monthly",
];

export const RECURRENCE_KIND_LABELS: Record<RecurrenceKind, string> = {
  every_minutes: "Every few minutes",
  hourly: "Every hour",
  daily: "Every day",
  weekly: "On chosen weekdays",
  monthly: "Once a month",
};

/** Which rhythms carry days at all. `weekly` needs them; the two that repeat within a day
 *  may have them, because the market is shut two days in seven. `daily` may not: daily on
 *  chosen days is `weekly`, and the module refuses the second way of saying it. */
export const RECURRENCE_KINDS_WITH_WEEKDAYS: readonly RecurrenceKind[] = [
  "every_minutes",
  "hourly",
  "weekly",
];

/** ISO days, the way the module numbers them: 1 is Monday, 7 is Sunday. */
export const WEEKDAYS: readonly { day: number; label: string }[] = [
  { day: 1, label: "Mon" },
  { day: 2, label: "Tue" },
  { day: 3, label: "Wed" },
  { day: 4, label: "Thu" },
  { day: 5, label: "Fri" },
  { day: 6, label: "Sat" },
  { day: 7, label: "Sun" },
];

/**
 * A rhythm of this kind, keeping whatever the previous one already answered — switching
 * from "every day at 9:00" to "on chosen weekdays" keeps 9:00 rather than starting the
 * hour over. Only the fields the new kind uses are carried: the module refuses a rhythm
 * carrying anything else, and a form that can build a refused shape is a form that
 * refuses on save for a reason the operator cannot see.
 */
export function recurrenceOfKind(kind: RecurrenceKind, previous: Recurrence | null): Recurrence {
  const hour = previous?.hour ?? 9;
  const minute = previous?.minute ?? 0;
  const base: Recurrence = {
    kind,
    minutes: null,
    minute: null,
    hour: null,
    weekdays: null,
    dayOfMonth: null,
  };
  // Days carry the same way the hour does, between the three rhythms that have them: an
  // operator narrowing "Mon–Fri at 9:00" to "every hour" keeps their week.
  const weekdays = previous?.weekdays ?? null;
  switch (kind) {
    case "every_minutes":
      return { ...base, minutes: previous?.minutes ?? 15, weekdays };
    case "hourly":
      return { ...base, minute, weekdays };
    case "daily":
      return { ...base, hour, minute };
    case "weekly":
      return { ...base, hour, minute, weekdays: weekdays ?? [1, 2, 3, 4, 5] };
    case "monthly":
      return { ...base, hour, minute, dayOfMonth: previous?.dayOfMonth ?? 1 };
  }
}

/** The days a rhythm actually fires on, spelled out. No days named means every one of
 *  them, and the toggles show that rather than seven empty boxes. */
export function chosenWeekdays(recurrence: Recurrence): number[] {
  return recurrence.weekdays ?? WEEKDAYS.map(({ day }) => day);
}

/**
 * One day switched on or off, in the shape the module stores.
 *
 * Every day chosen is written as no days at all, exactly as the module normalises it — so
 * the form never holds two states for one trigger and the operator cannot wonder which of
 * them they saved. `weekly` is the exception: its days are required, so seven days stay
 * seven days there and remain their own expression.
 *
 * The last day cannot be taken away. A rhythm that fires on no day is one the module
 * refuses, and the refusal would arrive on save with the form already looking finished.
 */
export function withWeekdayToggled(recurrence: Recurrence, day: number): Recurrence {
  const chosen = chosenWeekdays(recurrence);
  const next = chosen.includes(day)
    ? chosen.length === 1
      ? chosen
      : chosen.filter((each) => each !== day)
    : [...chosen, day].sort((a, b) => a - b);
  const everyDay = next.length === WEEKDAYS.length && recurrence.kind !== "weekly";
  return { ...recurrence, weekdays: everyDay ? null : next };
}

/** Switching between the wizard and the expression underneath it. Exactly one of the two
 *  is ever set, which is what the module's own wire demands. */
export function withTiming(
  draft: ScheduleDraft,
  timing: { recurrence: Recurrence } | { cronExpression: string },
): ScheduleDraft {
  return "recurrence" in timing
    ? { ...draft, recurrence: timing.recurrence, cronExpression: null }
    : { ...draft, recurrence: null, cronExpression: timing.cronExpression };
}

function clock(hour: number | null, minute: number | null): string {
  return `${String(hour ?? 0).padStart(2, "0")}:${String(minute ?? 0).padStart(2, "0")}`;
}

function dayLabels(weekdays: readonly number[]): string {
  return weekdays
    .map((day) => WEEKDAYS.find((weekday) => weekday.day === day)?.label ?? day)
    .join(", ");
}

/** The days clause of a rhythm that need not have one — empty when it fires on all of
 *  them, because "every hour, Mon to Sun" is a longer way of saying "every hour". */
function onDays(recurrence: Recurrence): string {
  return recurrence.weekdays === null ? "" : `, ${dayLabels(recurrence.weekdays)}`;
}

/** What a rhythm says, in a line. A label, not a calculation: when the schedule actually
 *  fires is the module's answer and is read from it (`previewNextFires`). */
export function describeRecurrence(recurrence: Recurrence): string {
  switch (recurrence.kind) {
    case "every_minutes":
      return `Every ${recurrence.minutes} minutes${onDays(recurrence)}`;
    case "hourly":
      return `Every hour at :${String(recurrence.minute ?? 0).padStart(2, "0")}${onDays(recurrence)}`;
    case "daily":
      return `Every day at ${clock(recurrence.hour, recurrence.minute)}`;
    case "weekly":
      return `${dayLabels(recurrence.weekdays ?? [])} at ${clock(recurrence.hour, recurrence.minute)}`;
    case "monthly":
      return `Day ${recurrence.dayOfMonth} of the month at ${clock(recurrence.hour, recurrence.minute)}`;
  }
}

/** How a saved schedule reads on the list: its rhythm, or the expression it is when no
 *  rhythm describes it. */
export function describeSchedule(schedule: Schedule): string {
  return schedule.recurrence === null
    ? schedule.cronExpression
    : describeRecurrence(schedule.recurrence);
}

export function emptyTriggerDraft(revisionId: number | null): TriggerDraft {
  return {
    revisionMode: "pinned",
    pinnedRevisionId: revisionId,
    toolName: "",
    arguments: {},
    fieldPath: "",
    comparison: "gt",
    threshold: "",
    cooldownSeconds: 900,
    pollIntervalSeconds: 300,
  };
}

/** Switching modes clears or restores `pinnedRevisionId` together with `revisionMode` —
 *  the pair the wire itself keeps coherent (`ScheduleIn`/`TriggerIn`'s own validator),
 *  so a draft here is never in the shape the module would refuse for that reason alone. */
export function withRevisionMode<T extends { revisionMode: RevisionMode; pinnedRevisionId: number | null }>(
  draft: T,
  mode: RevisionMode,
  latestRevisionId: number | null,
): T {
  return { ...draft, revisionMode: mode, pinnedRevisionId: mode === "pinned" ? latestRevisionId : null };
}

export const TRIGGER_COMPARISONS: readonly TriggerComparison[] = ["gt", "gte", "lt", "lte", "eq"];

export const COMPARISON_LABELS: Record<TriggerComparison, string> = {
  gt: ">",
  gte: "≥",
  lt: "<",
  lte: "≤",
  eq: "=",
};
