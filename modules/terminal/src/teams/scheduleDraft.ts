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
    unattendedAck: false,
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
    unattendedAck: schedule.unattendedAck,
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
  switch (kind) {
    case "every_minutes":
      return { ...base, minutes: previous?.minutes ?? 15 };
    case "hourly":
      return { ...base, minute };
    case "daily":
      return { ...base, hour, minute };
    case "weekly":
      return { ...base, hour, minute, weekdays: previous?.weekdays ?? [1, 2, 3, 4, 5] };
    case "monthly":
      return { ...base, hour, minute, dayOfMonth: previous?.dayOfMonth ?? 1 };
  }
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

/** What a rhythm says, in a line. A label, not a calculation: when the schedule actually
 *  fires is the module's answer and is read from it (`previewNextFires`). */
export function describeRecurrence(recurrence: Recurrence): string {
  switch (recurrence.kind) {
    case "every_minutes":
      return `Every ${recurrence.minutes} minutes`;
    case "hourly":
      return `Every hour at :${String(recurrence.minute ?? 0).padStart(2, "0")}`;
    case "daily":
      return `Every day at ${clock(recurrence.hour, recurrence.minute)}`;
    case "weekly": {
      const days = (recurrence.weekdays ?? [])
        .map((day) => WEEKDAYS.find((weekday) => weekday.day === day)?.label ?? day)
        .join(", ");
      return `${days} at ${clock(recurrence.hour, recurrence.minute)}`;
    }
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
    unattendedAck: false,
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
