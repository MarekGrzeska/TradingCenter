import { useEffect, useState } from "react";
import { MarketDataError } from "../data/types";
import { ModalShell } from "../ui/ModalShell";
import { browserIsInScheduleZone, formatBrowserInstant, formatInstant } from "../ui/formatTime";
import {
  RECURRENCE_KINDS,
  RECURRENCE_KINDS_WITH_WEEKDAYS,
  RECURRENCE_KIND_LABELS,
  WEEKDAYS,
  chosenWeekdays,
  emptyScheduleDraft,
  draftFromSchedule,
  recurrenceOfKind,
  withRevisionMode,
  withTiming,
  withWeekdayToggled,
} from "./scheduleDraft";
import type {
  Recurrence,
  RecurrenceKind,
  Schedule,
  ScheduleDraft,
  TeamsApi,
} from "./teamsApi";

/**
 * Where a schedule is made: a rhythm, a time of day, and the days it applies to — no cron
 * expression unless the operator goes looking for one (specs/terminal-teams-schedules,
 * "Harmonogram układa się rytmem i godziną, nie wyrażeniem czasowym").
 *
 * **Nothing here works out when the schedule fires.** The preview under the form is the
 * module's own answer for the draft as it stands (`api.previewNextFires`), which is also
 * what makes it trustworthy: it is computed by the same code the clock runs, in the same
 * zone, rather than by a second implementation that agrees until it doesn't.
 *
 * The expression is still reachable, under "Advanced" — a schedule the wizard cannot
 * describe (a range, two hours in one line) opens there and MUST leave unchanged.
 */
export function ScheduleWizardDialog({
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
    schedule === null ? emptyScheduleDraft(latestRevisionId) : draftFromSchedule(schedule),
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      setError(
        cause instanceof MarketDataError && cause.kind === "refused"
          ? cause.message
          : cause instanceof Error
            ? cause.message
            : "could not save the schedule",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <ModalShell
      title={schedule === null ? "New schedule" : "Edit schedule"}
      closeDisabled={saving}
      showCloseButton
      onClose={onClose}
      footer={
        <div className="flex flex-col gap-2">
          {error && <p className="text-critical">{error}</p>}
          <div className="flex justify-end gap-2">
            <button
              type="button"
              disabled={saving}
              onClick={onClose}
              className="rounded border border-border px-3 py-1 text-ink-muted hover:text-ink disabled:opacity-40"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={saving}
              onClick={save}
              className="rounded border border-primary bg-primary-soft px-3 py-1 text-ink hover:bg-primary-strong hover:text-ink-inverse disabled:opacity-40"
            >
              {saving ? "Saving…" : schedule === null ? "Create schedule" : "Save schedule"}
            </button>
          </div>
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        {draft.recurrence !== null ? (
          <RhythmFields
            recurrence={draft.recurrence}
            onChange={(recurrence) => setDraft(withTiming(draft, { recurrence }))}
          />
        ) : (
          <p className="text-xs text-ink-muted">
            This schedule is written as an expression the wizard has no rhythm for. It is
            under <span className="text-ink">Advanced</span>, unchanged.
          </p>
        )}

        <NextFiresPreview api={api} draft={draft} />

        <label className="flex items-center gap-2 text-xs text-ink-muted">
          <input
            type="checkbox"
            checked={draft.revisionMode === "latest"}
            onChange={(event) =>
              setDraft(
                withRevisionMode(draft, event.target.checked ? "latest" : "pinned", latestRevisionId),
              )
            }
          />
          Follow the team's latest revision
          {draft.revisionMode === "pinned" && draft.pinnedRevisionId !== null && (
            <span className="text-ink-faint">(pinned to revision id {draft.pinnedRevisionId})</span>
          )}
        </label>

        <label className="flex items-center gap-2 text-xs text-ink-muted">
          <input
            type="checkbox"
            checked={draft.unattendedAck}
            onChange={(event) => setDraft({ ...draft, unattendedAck: event.target.checked })}
          />
          I understand this runs without an operator watching
        </label>

        <details open={draft.recurrence === null} className="rounded border border-border p-2">
          <summary className="cursor-pointer text-xs text-ink-muted">Advanced (cron)</summary>
          <div className="mt-2 flex flex-col gap-2">
            <label className="text-xs text-ink-muted" htmlFor="schedule-cron">
              Five-field cron, read as a wall clock in Poland
            </label>
            <input
              id="schedule-cron"
              value={draft.cronExpression ?? ""}
              placeholder="0 9 * * MON-FRI"
              onChange={(event) => setDraft(withTiming(draft, { cronExpression: event.target.value }))}
              className="rounded border border-border bg-panel px-2 py-1 font-mono text-sm text-ink"
            />
            {draft.cronExpression !== null && (
              <button
                type="button"
                onClick={() =>
                  setDraft(withTiming(draft, { recurrence: recurrenceOfKind("daily", null) }))
                }
                className="self-start rounded border border-border px-2 py-1 text-xs text-ink hover:bg-panel-strong"
              >
                Back to the wizard
              </button>
            )}
          </div>
        </details>
      </div>
    </ModalShell>
  );
}

const INPUT = "rounded border border-border bg-panel px-2 py-1 text-sm text-ink";

function RhythmFields({
  recurrence,
  onChange,
}: {
  recurrence: Recurrence;
  onChange(next: Recurrence): void;
}) {
  return (
    <div className="flex flex-col gap-3">
      <fieldset className="flex flex-col gap-1">
        <legend className="mb-1 text-xs text-ink-muted">How often?</legend>
        <div className="flex flex-wrap gap-2">
          {RECURRENCE_KINDS.map((kind) => (
            <label
              key={kind}
              className={`cursor-pointer rounded border px-2 py-1 text-xs ${
                recurrence.kind === kind
                  ? "border-primary bg-primary-soft text-ink"
                  : "border-border text-ink-muted hover:bg-panel-strong"
              }`}
            >
              <input
                type="radio"
                name="recurrence-kind"
                className="sr-only"
                checked={recurrence.kind === kind}
                onChange={() => onChange(recurrenceOfKind(kind as RecurrenceKind, recurrence))}
              />
              {RECURRENCE_KIND_LABELS[kind]}
            </label>
          ))}
        </div>
      </fieldset>

      {recurrence.kind === "every_minutes" && (
        <label className="flex items-center gap-2 text-xs text-ink-muted">
          Every
          <input
            type="number"
            min={1}
            max={59}
            aria-label="Minutes between runs"
            value={recurrence.minutes ?? 15}
            onChange={(event) => onChange({ ...recurrence, minutes: Number(event.target.value) })}
            className={`${INPUT} w-20`}
          />
          minutes
        </label>
      )}

      {recurrence.kind === "hourly" && (
        <label className="flex items-center gap-2 text-xs text-ink-muted">
          At minute
          <input
            type="number"
            min={0}
            max={59}
            aria-label="Minute of the hour"
            value={recurrence.minute ?? 0}
            onChange={(event) => onChange({ ...recurrence, minute: Number(event.target.value) })}
            className={`${INPUT} w-20`}
          />
          of every hour
        </label>
      )}

      {(recurrence.kind === "daily" ||
        recurrence.kind === "weekly" ||
        recurrence.kind === "monthly") && (
        <label className="flex items-center gap-2 text-xs text-ink-muted">
          At
          <input
            type="time"
            aria-label="Time of day"
            value={`${pad(recurrence.hour)}:${pad(recurrence.minute)}`}
            onChange={(event) => onChange({ ...recurrence, ...readClock(event.target.value) })}
            className={INPUT}
          />
          Polish time
        </label>
      )}

      {RECURRENCE_KINDS_WITH_WEEKDAYS.includes(recurrence.kind) && (
        <fieldset className="flex flex-col gap-1">
          <legend className="mb-1 text-xs text-ink-muted">On which days?</legend>
          <div className="flex flex-wrap gap-1">
            {WEEKDAYS.map(({ day, label }) => {
              const chosen = chosenWeekdays(recurrence).includes(day);
              return (
                <button
                  key={day}
                  type="button"
                  aria-pressed={chosen}
                  onClick={() => onChange(withWeekdayToggled(recurrence, day))}
                  className={`cursor-pointer rounded border px-2 py-1 text-xs ${
                    chosen
                      ? "border-primary bg-primary-soft text-ink"
                      : "border-border text-ink-muted hover:bg-panel-strong"
                  }`}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </fieldset>
      )}

      {recurrence.kind === "monthly" && (
        <label className="flex items-center gap-2 text-xs text-ink-muted">
          On day
          <input
            type="number"
            min={1}
            max={31}
            aria-label="Day of the month"
            value={recurrence.dayOfMonth ?? 1}
            onChange={(event) => onChange({ ...recurrence, dayOfMonth: Number(event.target.value) })}
            className={`${INPUT} w-20`}
          />
          of the month
        </label>
      )}
    </div>
  );
}

function pad(value: number | null): string {
  return String(value ?? 0).padStart(2, "0");
}

/** `<input type="time">` hands back `HH:MM`; a browser that hands back nothing (the field
 *  cleared) leaves the rhythm where it was rather than at midnight. */
function readClock(value: string): { hour: number; minute: number } | Record<string, never> {
  const [hour, minute] = value.split(":");
  if (hour === undefined || minute === undefined) return {};
  return { hour: Number(hour), minute: Number(minute) };
}

/**
 * The draft's next few fires, from the module. Re-asked on every change of the timing,
 * one request behind a short wait so that dragging a number field does not send one per
 * keystroke; the previous request is aborted rather than raced.
 */
function NextFiresPreview({ api, draft }: { api: TeamsApi; draft: ScheduleDraft }) {
  const [times, setTimes] = useState<number[] | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const timing = JSON.stringify({ recurrence: draft.recurrence, cronExpression: draft.cronExpression });

  useEffect(() => {
    const controller = new AbortController();
    const asked = window.setTimeout(() => {
      api
        .previewNextFires(JSON.parse(timing) as ScheduleDraft, 3, controller.signal)
        .then((answer) => {
          setTimes(answer);
          setRefusal(null);
        })
        .catch((cause: unknown) => {
          if (controller.signal.aborted) return;
          setTimes(null);
          setRefusal(cause instanceof Error ? cause.message : "the module could not read this timing");
        });
    }, 250);
    return () => {
      window.clearTimeout(asked);
      controller.abort();
    };
  }, [api, timing]);

  return (
    <div className="rounded border border-border bg-panel px-3 py-2 text-xs">
      <div className="mb-1 text-ink-muted">Next fires</div>
      {refusal !== null && <p className="text-critical">{refusal}</p>}
      {refusal === null && times === null && <p className="text-ink-faint">Asking the module…</p>}
      {refusal === null &&
        times !== null &&
        times.map((time) => (
          <div key={time} className="text-ink">
            {formatInstant(time)}
            {!browserIsInScheduleZone() && (
              <span className="text-ink-faint"> · {formatBrowserInstant(time)}</span>
            )}
          </div>
        ))}
    </div>
  );
}
