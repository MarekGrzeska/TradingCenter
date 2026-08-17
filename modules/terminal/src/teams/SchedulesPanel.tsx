import { useEffect, useState } from "react";
import { useAgentTurns } from "../agent/useAgentTurns";
import { MarketDataError } from "../data/types";
import { formatInstant, formatUtcInstant } from "../ui/formatTime";
import { FireHistoryList } from "./FireHistoryList";
import {
  COMPARISON_LABELS,
  TRIGGER_COMPARISONS,
  emptyScheduleDraft,
  emptyTriggerDraft,
  withRevisionMode,
} from "./scheduleDraft";
import type {
  RevisionMode,
  Schedule,
  ScheduleDraft,
  ScheduleFire,
  TeamsApi,
  TeamsTool,
  Trigger,
  TriggerDraft,
} from "./teamsApi";

const INPUT = "rounded border border-border bg-panel px-2 py-1 text-sm text-ink";
const BUTTON = "cursor-pointer rounded border border-border px-2 py-1 text-xs text-ink hover:bg-panel-strong";
const PRIMARY_BUTTON =
  "cursor-pointer rounded border border-primary-line bg-primary-soft px-3 py-1 text-xs text-ink hover:bg-primary-strong hover:text-ink-inverse disabled:cursor-not-allowed disabled:opacity-40";

/**
 * A team's own clock: the schedules that fire it on time, and the triggers that fire it
 * on a market condition — `terminal-teams-schedules`. Both fire the same shape of thing
 * (a run, or a row explaining why not), so they share this one view and the fire history
 * beneath each (`FireHistoryList.tsx`).
 *
 * Nothing here computes a moment to fire at, or evaluates a condition — every timestamp
 * and every `enabled`/`disabledReason` shown is read straight from the module's own
 * answer (`terminal-teams-schedules`, "Terminal nie liczy czasu wyzwolenia sam").
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
  const [latestRevisionId, setLatestRevisionId] = useState<number | null>(null);
  const [schedules, setSchedules] = useState<Schedule[] | null>(null);
  const [triggers, setTriggers] = useState<Trigger[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadCount, setReloadCount] = useState(0);
  const reload = () => setReloadCount((n) => n + 1);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    Promise.all([
      api.latestRevision(teamId, controller.signal),
      api.listSchedules(teamId, controller.signal),
      api.listTriggers(teamId, controller.signal),
    ])
      .then(([revision, scheduleList, triggerList]) => {
        if (cancelled) return;
        setLatestRevisionId(revision.id);
        setSchedules(scheduleList);
        setTriggers(triggerList);
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setLoadError(cause instanceof Error ? cause.message : "could not read schedules and triggers");
        }
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [api, teamId, reloadCount]);

  // `schedule_team` and `trigger_team` are chat tools too, and nothing about them reaches
  // this panel — the same staleness the catalogue had (`agentActivity.ts`). Everything on
  // screen here is a read of the module's own rows, so re-reading costs nothing but the
  // three requests above; the form being filled in is local state and is left alone.
  useAgentTurns(reload);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex items-center gap-2 border-b border-border p-2">
        <button type="button" onClick={onClose} className={BUTTON}>
          ← {teamName}
        </button>
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

// --- schedules --------------------------------------------------------------------

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

  return (
    <section className="mb-6">
      <div className="mb-2 flex items-center gap-2">
        <h3 className="text-sm font-medium text-ink">Schedules</h3>
        <button type="button" onClick={() => setEditing("new")} className={BUTTON}>
          New schedule
        </button>
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
                  <code>{schedule.cronExpression}</code>{" "}
                  <span className="text-xs text-ink-faint">
                    ({schedule.revisionMode === "pinned" ? `revision pinned` : "tracks latest"})
                  </span>
                </div>
                <div className="text-xs text-ink-muted">
                  next fire {formatUtcInstant(schedule.nextFireAt)} · local{" "}
                  {formatInstant(schedule.nextFireAt)}
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
                <button type="button" onClick={() => setEditing(schedule)} className={BUTTON}>
                  Edit
                </button>
                <button
                  type="button"
                  onClick={() => setHistoryFor(historyFor === schedule.id ? null : schedule.id)}
                  className={BUTTON}
                >
                  History
                </button>
              </div>
            </div>
            {historyFor === schedule.id && (
              <div className="mt-2 border-t border-border pt-2">
                <ScheduleHistory api={api} scheduleId={schedule.id} onWatchRun={onWatchRun} />
              </div>
            )}
          </li>
        ))}
      </ul>

      {editing !== null && (
        <ScheduleForm
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
    </section>
  );
}

/**
 * The one control here that changes something without a form around it — so it carries
 * its own refusal, in the module's words, the same way `ScheduleForm.save` does
 * (`terminal-teams-schedules`, "Odmowa modułu jest pokazana słowami modułu"). Without
 * this the failed call was invisible: the button simply went back to saying what it said
 * before, and the rejection went to the console.
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
      <button
        type="button"
        disabled={busy}
        onClick={() => {
          setBusy(true);
          setError(null);
          Promise.resolve(enabled ? onDisable() : onEnable())
            .catch((cause: unknown) =>
              setError(refusalMessage(cause, enabled ? "could not disable it" : "could not enable it")),
            )
            .finally(() => setBusy(false));
        }}
        className={`${BUTTON} disabled:cursor-not-allowed disabled:opacity-40`}
      >
        {enabled ? "Disable" : "Enable"}
      </button>
      {error && <span className="text-right text-xs text-critical">{error}</span>}
    </div>
  );
}

function ScheduleHistory({
  api,
  scheduleId,
  onWatchRun,
}: {
  api: TeamsApi;
  scheduleId: number;
  onWatchRun(runId: number): void;
}) {
  const [fires, setFires] = useState<ScheduleFire[] | null>(null);
  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    api
      .scheduleFires(scheduleId, controller.signal)
      .then((answer) => !cancelled && setFires(answer))
      .catch(() => !cancelled && setFires([]));
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [api, scheduleId]);

  return <FireHistoryList fires={fires} onWatchRun={onWatchRun} />;
}

function ScheduleForm({
  api,
  teamId,
  schedule,
  latestRevisionId,
  onClose,
  onSaved,
}: {
  api: TeamsApi;
  teamId: number;
  /** `null` creates a new schedule. */
  schedule: Schedule | null;
  latestRevisionId: number | null;
  onClose(): void;
  onSaved(): void;
}) {
  const [draft, setDraft] = useState<ScheduleDraft>(
    schedule ?? emptyScheduleDraft(latestRevisionId),
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nextFires, setNextFires] = useState<number[] | null>(null);

  useEffect(() => {
    if (schedule === null) return;
    let cancelled = false;
    const controller = new AbortController();
    api
      .nextFires(schedule.id, 5, controller.signal)
      .then((times) => !cancelled && setNextFires(times))
      .catch(() => !cancelled && setNextFires(null));
    return () => {
      cancelled = true;
      controller.abort();
    };
    // Re-read only when the row this form opened on changes — not on every keystroke,
    // since the preview is the *saved* schedule's own next fires, not the draft's.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, schedule?.id]);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      if (schedule === null) {
        await api.createSchedule(teamId, draft, new AbortController().signal);
      } else {
        await api.updateSchedule(schedule.id, draft, new AbortController().signal);
      }
      onSaved();
    } catch (cause) {
      setError(refusalMessage(cause, "could not save the schedule"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mt-3 flex flex-col gap-2 rounded border border-border bg-panel-strong p-3">
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-xs text-ink-muted" htmlFor="schedule-cron">
          Cron
        </label>
        <input
          id="schedule-cron"
          value={draft.cronExpression}
          onChange={(event) => setDraft({ ...draft, cronExpression: event.target.value })}
          placeholder="*/5 * * * *"
          className={`${INPUT} font-mono`}
        />
        <RevisionModeFields
          revisionMode={draft.revisionMode}
          pinnedRevisionId={draft.pinnedRevisionId}
          onChangeMode={(mode) => setDraft(withRevisionMode(draft, mode, latestRevisionId))}
        />
      </div>

      <UnattendedAckField
        checked={draft.unattendedAck}
        onChange={(unattendedAck) => setDraft({ ...draft, unattendedAck })}
      />

      {nextFires !== null && nextFires.length > 0 && (
        <div className="text-xs text-ink-muted">
          Next: {nextFires.map((t) => formatUtcInstant(t)).join(" · ")}
        </div>
      )}

      {error && <p className="text-xs text-critical">{error}</p>}

      <div className="flex gap-2">
        <button type="button" onClick={save} disabled={saving} className={PRIMARY_BUTTON}>
          {saving ? "Saving…" : schedule === null ? "Create schedule" : "Save schedule"}
        </button>
        <button type="button" onClick={onClose} className={BUTTON}>
          Cancel
        </button>
      </div>
    </div>
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

function UnattendedAckField({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange(next: boolean): void;
}) {
  return (
    <label className="flex items-center gap-1 text-xs text-ink-muted">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      I understand this runs without an operator watching
    </label>
  );
}

// --- triggers -----------------------------------------------------------------------

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
        <button type="button" onClick={() => setEditing("new")} className={BUTTON}>
          New trigger
        </button>
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
                <button type="button" onClick={() => setEditing(trigger)} className={BUTTON}>
                  Edit
                </button>
                <button
                  type="button"
                  onClick={() => setHistoryFor(historyFor === trigger.id ? null : trigger.id)}
                  className={BUTTON}
                >
                  History
                </button>
              </div>
            </div>
            {historyFor === trigger.id && (
              <div className="mt-2 border-t border-border pt-2">
                <TriggerHistory api={api} triggerId={trigger.id} onWatchRun={onWatchRun} />
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

function TriggerHistory({
  api,
  triggerId,
  onWatchRun,
}: {
  api: TeamsApi;
  triggerId: number;
  onWatchRun(runId: number): void;
}) {
  const [fires, setFires] = useState<ScheduleFire[] | null>(null);
  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    api
      .triggerFires(triggerId, controller.signal)
      .then((answer) => !cancelled && setFires(answer))
      .catch(() => !cancelled && setFires([]));
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [api, triggerId]);

  return <FireHistoryList fires={fires} onWatchRun={onWatchRun} />;
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

      <UnattendedAckField
        checked={draft.unattendedAck}
        onChange={(unattendedAck) => setDraft({ ...draft, unattendedAck })}
      />

      {error && <p className="text-xs text-critical">{error}</p>}

      <div className="flex gap-2">
        <button
          type="button"
          onClick={save}
          disabled={saving || argumentsError !== null || draft.toolName === ""}
          className={PRIMARY_BUTTON}
        >
          {saving ? "Saving…" : trigger === null ? "Create trigger" : "Save trigger"}
        </button>
        <button type="button" onClick={onClose} className={BUTTON}>
          Cancel
        </button>
      </div>
    </div>
  );
}
