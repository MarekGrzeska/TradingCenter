import { useState } from "react";
import { Button } from "../ui/Button";
import type { QueryKey } from "@tanstack/react-query";
import { useAgentTurns } from "../agent/useAgentTurns";
import { useRead } from "../data/query";
import { MarketDataError } from "../data/types";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { formatInstant } from "../ui/formatTime";
import { FireHistoryList } from "./FireHistoryList";
import { ScheduleWizardDialog } from "./ScheduleWizardDialog";
import {
  COMPARISON_LABELS,
  TRIGGER_COMPARISONS,
  describeSchedule,
  emptyTriggerDraft,
  withRevisionMode,
} from "./scheduleDraft";
import type {
  RevisionMode,
  Schedule,
  ScheduleFire,
  TeamsApi,
  TeamsTool,
  Trigger,
  TriggerDraft,
} from "./teamsApi";

/** Before the first answer: no revision to pin to, and neither list read yet — which the
 *  sections below draw as "loading", not as "this team has no rules". */
const NOT_READ_YET: {
  latestRevisionId: number | null;
  schedules: Schedule[] | null;
  triggers: Trigger[] | null;
} = { latestRevisionId: null, schedules: null, triggers: null };
const NO_FIRES: ScheduleFire[] = [];

const INPUT = "rounded border border-border bg-panel px-2 py-1 text-sm text-ink";

/**
 * A team's own clock: schedules that fire it on time, triggers that fire it on a market condition. Nothing here
 * computes a moment or evaluates a condition (`terminal-teams-schedules`, "Terminal nie liczy czasu…").
 */
export function SchedulesPanel({
  api,
  teamId,
  teamName,
  tools,
  onClose,
  onWatchRun,
}: {
  api: TeamsApi;
  teamId: number;
  teamName: string;
  tools: TeamsTool[];
  onClose(): void;
  onWatchRun(runId: number): void;
}) {
  // One read over all three, because the panel has one loading state and one failure: a rule list without the
  // revision it may pin to is a panel that cannot say which revision "latest" means.
  const rules = useRead({
    key: ["teams", teamId, "rules"],
    read: async (signal) => {
      const [revision, schedules, triggers] = await Promise.all([
        api.latestRevision(teamId, signal),
        api.listSchedules(teamId, signal),
        api.listTriggers(teamId, signal),
      ]);
      return { latestRevisionId: revision.id, schedules, triggers };
    },
    initial: NOT_READ_YET,
    fallbackMessage: "could not read schedules and triggers",
  });
  const { latestRevisionId, schedules, triggers } = rules.value;
  const loadError = rules.error;
  const reload = rules.reload;

  // `schedule_team` and `trigger_team` are chat tools too, and nothing about them reaches this panel — the
  // same staleness the catalogue had. Re-reading costs three requests; the form being filled in is left alone.
  useAgentTurns(reload);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex items-center gap-2 border-b border-border p-2">
        <Button onClick={onClose}>
          ← {teamName}
        </Button>
        <h2 className="text-sm font-semibold text-ink">Schedules and triggers</h2>
      </header>

      <div className="flex-1 overflow-auto p-4">
        {loadError && <p className="mb-3 text-sm text-critical">{loadError}</p>}

        <ScheduleSection
          api={api}
          teamId={teamId}
          schedules={schedules}
          latestRevisionId={latestRevisionId}
          onChanged={reload}
          onWatchRun={onWatchRun}
        />

        <TriggerSection
          api={api}
          teamId={teamId}
          triggers={triggers}
          tools={tools}
          latestRevisionId={latestRevisionId}
          onChanged={reload}
          onWatchRun={onWatchRun}
        />
      </div>
    </div>
  );
}

function refusalMessage(cause: unknown, fallback: string): string {
  if (cause instanceof MarketDataError && cause.kind === "refused") return cause.message;
  return cause instanceof Error ? cause.message : fallback;
}

function ScheduleSection({
  api,
  teamId,
  schedules,
  latestRevisionId,
  onChanged,
  onWatchRun,
}: {
  api: TeamsApi;
  teamId: number;
  schedules: Schedule[] | null;
  latestRevisionId: number | null;
  onChanged(): void;
  onWatchRun(runId: number): void;
}) {
  const [editing, setEditing] = useState<"new" | Schedule | null>(null);
  const [historyFor, setHistoryFor] = useState<number | null>(null);
  const [deleting, setDeleting] = useState<Schedule | null>(null);

  return (
    <section className="mb-6">
      <div className="mb-2 flex items-center gap-2">
        <h3 className="text-sm font-medium text-ink">Schedules</h3>
        <Button onClick={() => setEditing("new")}>
          New schedule
        </Button>
      </div>

      {schedules === null && <p className="text-xs text-ink-muted">Reading schedules…</p>}
      {schedules !== null && schedules.length === 0 && (
        <p className="text-xs text-ink-muted">No schedules yet — this team only runs by hand.</p>
      )}

      <ul className="flex flex-col gap-2">
        {(schedules ?? []).map((schedule) => (
          <li key={schedule.id} className="rounded border border-border bg-panel px-3 py-2">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate text-sm text-ink">
                  {describeSchedule(schedule)}{" "}
                  <span className="text-xs text-ink-faint">
                    ({schedule.revisionMode === "pinned" ? `revision pinned` : "tracks latest"})
                  </span>
                </div>
                <div className="text-xs text-ink-muted">
                  next fire {formatInstant(schedule.nextFireAt)}
                </div>
                {!schedule.enabled && (
                  <div className="text-xs text-critical">
                    disabled{schedule.disabledReason !== null && ` — ${schedule.disabledReason}`}
                  </div>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <EnableToggle
                  enabled={schedule.enabled}
                  onEnable={() => api.enableSchedule(schedule.id, new AbortController().signal).then(onChanged)}
                  onDisable={() => api.disableSchedule(schedule.id, new AbortController().signal).then(onChanged)}
                />
                <Button onClick={() => setEditing(schedule)}>
                  Edit
                </Button>
                <Button onClick={() => setHistoryFor(historyFor === schedule.id ? null : schedule.id)}>
                  History
                </Button>
                <Button onClick={() => setDeleting(schedule)}>
                  Delete
                </Button>
              </div>
            </div>
            {historyFor === schedule.id && (
              <div className="mt-2 border-t border-border pt-2">
                <FireHistory
                  ruleKey={["teams", "schedule", schedule.id, "fires"]}
                  read={(signal) => api.scheduleFires(schedule.id, signal)}
                  onWatchRun={onWatchRun}
                />
              </div>
            )}
          </li>
        ))}
      </ul>

      {editing !== null && (
        <ScheduleWizardDialog
          api={api}
          teamId={teamId}
          schedule={editing === "new" ? null : editing}
          latestRevisionId={latestRevisionId}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            onChanged();
          }}
        />
      )}

      {deleting && (
        <ConfirmDialog
          title="Delete this schedule?"
          confirmLabel="Delete"
          busyLabel="Deleting…"
          tone="danger"
          fallbackError="the schedule could not be deleted"
          onConfirm={async () => {
            await api.deleteSchedule(deleting.id, new AbortController().signal);
            onChanged();
          }}
          onClose={() => setDeleting(null)}
        >
          <p className="text-sm text-ink">{describeSchedule(deleting)}</p>
          <p className="mt-2 text-sm text-ink">
            Its fire history goes with it and does not come back. The runs it started stay,
            with what they cost and anything they traded.
          </p>
          <p className="mt-2 text-xs text-ink-muted">
            To stop it from firing without losing any of that, disable it instead.
          </p>
        </ConfirmDialog>
      )}
    </section>
  );
}

/**
 * The one control here that changes something without a form around it, so it carries its own refusal in the
 * module's words: without this the failed call was invisible and the rejection went to the console.
 */
function EnableToggle({
  enabled,
  onEnable,
  onDisable,
}: {
  enabled: boolean;
  onEnable(): Promise<unknown>;
  onDisable(): Promise<unknown>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <div className="flex flex-col items-end gap-1">
      <Button disabled={busy} onClick={() => { setBusy(true); setError(null); Promise.resolve(enabled ? onDisable() : onEnable()) .catch((cause: unknown) => setError(refusalMessage(cause, enabled ? "could not disable it" : "could not enable it")), ) .finally(() => setBusy(false)); }}>
        {enabled ? "Disable" : "Enable"}
      </Button>
      {error && <span className="text-right text-xs text-critical">{error}</span>}
    </div>
  );
}

/**
 * A schedule's fires and a trigger's are the same rows read through two routes, so they are one component. A
 * history that cannot be read renders empty: its failure is already reported at the top of the panel.
 */
function FireHistory({
  ruleKey,
  read,
  onWatchRun,
}: {
  /** What tells this rule's history from every other one in the cache. */
  ruleKey: QueryKey;
  read(signal: AbortSignal): Promise<ScheduleFire[]>;
  onWatchRun(runId: number): void;
}) {
  const history = useRead({
    key: ruleKey,
    read,
    initial: NO_FIRES,
    fallbackMessage: "could not read the fire history",
  });

  return (
    <FireHistoryList
      fires={history.status === "loading" ? null : history.value}
      onWatchRun={onWatchRun}
    />
  );
}

function RevisionModeFields({
  revisionMode,
  pinnedRevisionId,
  onChangeMode,
}: {
  revisionMode: RevisionMode;
  pinnedRevisionId: number | null;
  onChangeMode(mode: RevisionMode): void;
}) {
  return (
    <label className="flex items-center gap-1 text-xs text-ink-muted">
      <input
        type="checkbox"
        checked={revisionMode === "latest"}
        onChange={(event) => onChangeMode(event.target.checked ? "latest" : "pinned")}
      />
      track latest revision
      {revisionMode === "pinned" && pinnedRevisionId !== null && (
        <span> (pinned to revision id {pinnedRevisionId})</span>
      )}
    </label>
  );
}

function TriggerSection({
  api,
  teamId,
  triggers,
  tools,
  latestRevisionId,
  onChanged,
  onWatchRun,
}: {
  api: TeamsApi;
  teamId: number;
  triggers: Trigger[] | null;
  tools: TeamsTool[];
  latestRevisionId: number | null;
  onChanged(): void;
  onWatchRun(runId: number): void;
}) {
  const [editing, setEditing] = useState<"new" | Trigger | null>(null);
  const [historyFor, setHistoryFor] = useState<number | null>(null);

  return (
    <section>
      <div className="mb-2 flex items-center gap-2">
        <h3 className="text-sm font-medium text-ink">Triggers</h3>
        <Button onClick={() => setEditing("new")}>
          New trigger
        </Button>
      </div>

      {triggers === null && <p className="text-xs text-ink-muted">Reading triggers…</p>}
      {triggers !== null && triggers.length === 0 && (
        <p className="text-xs text-ink-muted">No triggers yet.</p>
      )}

      <ul className="flex flex-col gap-2">
        {(triggers ?? []).map((trigger) => (
          <li key={trigger.id} className="rounded border border-border bg-panel px-3 py-2">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate text-sm text-ink">
                  <code>{trigger.toolName}</code>.{trigger.fieldPath}{" "}
                  {COMPARISON_LABELS[trigger.comparison]} {trigger.threshold}
                </div>
                <div className="text-xs text-ink-muted">
                  last read:{" "}
                  {trigger.lastResult === null
                    ? "unknown — the tool server could not be asked"
                    : trigger.lastResult
                      ? "condition met"
                      : "not met"}
                  {trigger.lastCheckedAt !== null && ` (${formatInstant(trigger.lastCheckedAt)})`}
                </div>
                {!trigger.enabled && (
                  <div className="text-xs text-critical">
                    disabled{trigger.disabledReason !== null && ` — ${trigger.disabledReason}`}
                  </div>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <EnableToggle
                  enabled={trigger.enabled}
                  onEnable={() => api.enableTrigger(trigger.id, new AbortController().signal).then(onChanged)}
                  onDisable={() => api.disableTrigger(trigger.id, new AbortController().signal).then(onChanged)}
                />
                <Button onClick={() => setEditing(trigger)}>
                  Edit
                </Button>
                <Button onClick={() => setHistoryFor(historyFor === trigger.id ? null : trigger.id)}>
                  History
                </Button>
              </div>
            </div>
            {historyFor === trigger.id && (
              <div className="mt-2 border-t border-border pt-2">
                <FireHistory
                  ruleKey={["teams", "trigger", trigger.id, "fires"]}
                  read={(signal) => api.triggerFires(trigger.id, signal)}
                  onWatchRun={onWatchRun}
                />
              </div>
            )}
          </li>
        ))}
      </ul>

      {editing !== null && (
        <TriggerForm
          api={api}
          teamId={teamId}
          trigger={editing === "new" ? null : editing}
          tools={tools}
          latestRevisionId={latestRevisionId}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            onChanged();
          }}
        />
      )}
    </section>
  );
}

function TriggerForm({
  api,
  teamId,
  trigger,
  tools,
  latestRevisionId,
  onClose,
  onSaved,
}: {
  api: TeamsApi;
  teamId: number;
  trigger: Trigger | null;
  tools: TeamsTool[];
  latestRevisionId: number | null;
  onClose(): void;
  onSaved(): void;
}) {
  const [draft, setDraft] = useState<TriggerDraft>(trigger ?? emptyTriggerDraft(latestRevisionId));
  const [argumentsText, setArgumentsText] = useState(JSON.stringify(draft.arguments));
  const [argumentsError, setArgumentsError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      if (trigger === null) {
        await api.createTrigger(teamId, draft, new AbortController().signal);
      } else {
        await api.updateTrigger(trigger.id, draft, new AbortController().signal);
      }
      onSaved();
    } catch (cause) {
      setError(refusalMessage(cause, "could not save the trigger"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mt-3 flex flex-col gap-2 rounded border border-border bg-panel-strong p-3">
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-xs text-ink-muted" htmlFor="trigger-tool">
          Tool
        </label>
        <select
          id="trigger-tool"
          value={draft.toolName}
          onChange={(event) => setDraft({ ...draft, toolName: event.target.value })}
          className={INPUT}
        >
          <option value="">— pick a tool —</option>
          {tools.map((tool) => (
            <option key={tool.name} value={tool.name}>
              {tool.name}
            </option>
          ))}
        </select>

        <label className="text-xs text-ink-muted" htmlFor="trigger-field">
          Field
        </label>
        <input
          id="trigger-field"
          value={draft.fieldPath}
          onChange={(event) => setDraft({ ...draft, fieldPath: event.target.value })}
          placeholder="value"
          className={`${INPUT} font-mono`}
        />

        <select
          aria-label="Comparison"
          value={draft.comparison}
          onChange={(event) => setDraft({ ...draft, comparison: event.target.value as TriggerDraft["comparison"] })}
          className={INPUT}
        >
          {TRIGGER_COMPARISONS.map((comparison) => (
            <option key={comparison} value={comparison}>
              {COMPARISON_LABELS[comparison]}
            </option>
          ))}
        </select>

        <input
          aria-label="Threshold"
          value={draft.threshold}
          onChange={(event) => setDraft({ ...draft, threshold: event.target.value })}
          placeholder="70"
          className={`${INPUT} w-24`}
        />
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-xs text-ink-muted" htmlFor="trigger-arguments">
          Arguments (JSON, whatever the tool needs)
        </label>
        <textarea
          id="trigger-arguments"
          value={argumentsText}
          onChange={(event) => {
            const text = event.target.value;
            setArgumentsText(text);
            try {
              const parsed: unknown = JSON.parse(text);
              if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
                throw new Error("must be a JSON object");
              }
              setDraft({ ...draft, arguments: parsed as Record<string, unknown> });
              setArgumentsError(null);
            } catch {
              setArgumentsError("not a valid JSON object");
            }
          }}
          rows={2}
          className={`${INPUT} font-mono`}
        />
        {argumentsError && <p className="text-xs text-critical">{argumentsError}</p>}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <label className="text-xs text-ink-muted" htmlFor="trigger-cooldown">
          Cooldown (s)
        </label>
        <input
          id="trigger-cooldown"
          type="number"
          min={1}
          value={draft.cooldownSeconds}
          onChange={(event) => setDraft({ ...draft, cooldownSeconds: Number(event.target.value) })}
          className={`${INPUT} w-24`}
        />
        <label className="text-xs text-ink-muted" htmlFor="trigger-poll">
          Check every (s)
        </label>
        <input
          id="trigger-poll"
          type="number"
          min={1}
          value={draft.pollIntervalSeconds}
          onChange={(event) => setDraft({ ...draft, pollIntervalSeconds: Number(event.target.value) })}
          className={`${INPUT} w-24`}
        />
        <RevisionModeFields
          revisionMode={draft.revisionMode}
          pinnedRevisionId={draft.pinnedRevisionId}
          onChangeMode={(mode) => setDraft(withRevisionMode(draft, mode, latestRevisionId))}
        />
      </div>

      {error && <p className="text-xs text-critical">{error}</p>}

      <div className="flex gap-2">
        <Button tone="primary" onClick={save} disabled={saving || argumentsError !== null || draft.toolName === ""}>
          {saving ? "Saving…" : trigger === null ? "Create trigger" : "Save trigger"}
        </Button>
        <Button onClick={onClose}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
