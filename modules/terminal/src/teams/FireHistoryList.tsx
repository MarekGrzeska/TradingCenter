import { formatInstant } from "../ui/formatTime";
import type { ScheduleFire } from "./teamsApi";
import { Button } from "../ui/Button";

/**
 * A schedule's or a trigger's fire history — including a fire that started nothing.
 * Shared between both, since `ScheduleFire` already is (`terminal-teams-schedules`,
 * "Historia pokazuje także to, co się nie wydarzyło"): a schedule that is quiet because
 * nothing was due looks identical to one quiet because it keeps hitting the daily
 * ceiling, unless the difference is written down — and this is where it is.
 */
export function FireHistoryList({
  fires,
  onWatchRun,
}: {
  fires: ScheduleFire[] | null;
  error?: string | null;
  onWatchRun(runId: number): void;
}) {
  if (fires === null) return <p className="text-xs text-ink-muted">Reading the history…</p>;
  if (fires.length === 0) return <p className="text-xs text-ink-muted">No fires yet.</p>;

  return (
    <ul className="flex flex-col gap-1">
      {fires.map((fire) => (
        <li
          key={fire.id}
          className="flex items-center justify-between gap-2 rounded border border-border px-2 py-1 text-xs"
        >
          <span className="min-w-0 truncate text-ink-muted">
            {formatInstant(fire.firedAt)} ·{" "}
            <span className={fire.outcome === "started" ? "text-ink" : "text-ink-faint"}>
              {fire.outcome}
            </span>
            {fire.skippedCount > 0 && ` · ${fire.skippedCount} folded in`}
            {fire.reason !== null && ` — ${fire.reason}`}
          </span>
          {fire.runId !== null && (
            <Button
              size="xs"
              className="shrink-0"
              onClick={() => onWatchRun(fire.runId!)}
            >
              Watch
            </Button>
          )}
        </li>
      ))}
    </ul>
  );
}
