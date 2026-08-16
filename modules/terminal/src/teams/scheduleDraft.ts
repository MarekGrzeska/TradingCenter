import type { RevisionMode, ScheduleDraft, TriggerComparison, TriggerDraft } from "./teamsApi";

/** A schedule pinned to `revisionId` — the default a fresh form opens on, mirroring
 *  specs/teams-schedules' own default ("Domyślnie MUST to być rewizja przypięta"). */
export function emptyScheduleDraft(revisionId: number | null): ScheduleDraft {
  return {
    revisionMode: "pinned",
    pinnedRevisionId: revisionId,
    cronExpression: "0 * * * *",
    unattendedAck: false,
  };
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
