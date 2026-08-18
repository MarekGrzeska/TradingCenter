import { useCallback, useMemo, useState } from "react";
import { UnreachableNotice } from "../ui/UnreachableNotice";
import { Link } from "react-router";
import { archive } from "../data/marketData";
import { RESOLUTIONS } from "../data/types";
import type { Chunk, JobPairView, JobStatus, PairDeletion, Resolution } from "../data/types";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { formatInstant } from "../ui/formatTime";
import { RESOLUTION_LABEL } from "../ui/resolutionLabel";
import { useJobHistory } from "./useJobHistory";
import type { JobHistoryState } from "./useJobHistory";

/**
 * Every pull the archive has run, per instrument and per interval — the
 * question `market-data-jobs` exists to answer without a log: what got
 * backfilled, how far a running one has got, and where to retry what
 * failed without touching the pair's archived status at all.
 */

/**
 * How long a running pull may show no sign of life before the tab says so.
 *
 * One chunk is one gateway request under the shared limiter, so five minutes is
 * comfortably above anything healthy and far below the forty minutes it took to
 * notice a job had stopped (proposal.md, Why). This is a display threshold, not
 * a judgement the archive makes: the fact is `lastActivityAt`, and calling it
 * worrying belongs to the view that already re-reads every ten seconds.
 */
const STALL_AFTER_SECONDS = 5 * 60;

/** "3 min", "2 h 10 min" — coarse on purpose. The question is "is anything
 *  happening", and seconds of precision would suggest an accuracy that a
 *  ten-second poll does not have. */
function elapsedLabel(seconds: number): string {
  if (seconds < 60) return "under a minute";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return `${hours} h ${minutes % 60} min`;
}

function secondsSince(moment: number): number {
  return Math.max(0, Math.floor(Date.now() / 1000) - moment);
}

const STATUS_LABEL: Record<JobStatus, string> = {
  running: "running",
  succeeded: "done",
  partial: "partial",
  failed: "failed",
  interrupted: "interrupted",
};

const STATUS_CLASS: Record<JobStatus, string> = {
  running: "text-ink-secondary",
  succeeded: "font-semibold text-good",
  partial: "font-semibold text-warning",
  failed: "font-semibold text-critical",
  interrupted: "font-semibold text-critical",
};

function chunkRange(chunks: Chunk[]): { start: number; end: number } | null {
  if (chunks.length === 0) return null;
  return {
    start: Math.min(...chunks.map((c) => c.chunkStart)),
    end: Math.max(...chunks.map((c) => c.chunkEnd)),
  };
}

/** How far back the work actually got, which is not always how far it was planned to.
 *
 *  A chunk is skipped when the provider turns out to have nothing below it, so a job
 *  asked for 2024 against an instrument whose history starts in 2026 plans the whole
 *  span and collects the top of it. Without this the row said "2024 → today, 0 candles",
 *  which reads as a failure and was a correct answer nobody could see. Derived from the
 *  chunks the row already carries — no field on the wire holds it. */
function collectedRange(chunks: Chunk[]): { start: number; end: number } | null {
  return chunkRange(chunks.filter((c) => c.state === "done"));
}

function failureReasons(chunks: Chunk[]): string[] {
  const reasons = new Set<string>();
  for (const chunk of chunks) {
    if (chunk.state === "failed") reasons.add(chunk.failure ?? "failed");
    else if (chunk.state === "interrupted") {
      reasons.add(chunk.failure ?? "interrupted by a module restart");
    }
  }
  return [...reasons];
}

/** One line of the combined timeline — a pull or a skasowanie, never
 *  confused for the other, since a job that succeeded and a deletion that
 *  undid it read very differently and MUST NOT share a row shape
 *  (terminal-collection-history spec, "Skasowanie odróżnia się od
 *  dociągnięcia"). */
type HistoryEntry =
  | { kind: "job"; at: number; symbol: string; resolution: Resolution; job: JobPairView }
  | { kind: "deletion"; at: number; symbol: string; resolution: Resolution; deletion: PairDeletion };

/**
 * Jobs and deletions, one instrument's story told in one order.
 *
 * A pull and the deletion that later undid it are two events about the same
 * pair, and splitting them into two lists would lose the "why does this
 * pair's range look shallower now" a reader is after — the deletion has to
 * sit right next to the pull it follows, not in a table of its own.
 */
function combinedEntries(rows: JobPairView[], deletions: PairDeletion[]): HistoryEntry[] {
  const entries: HistoryEntry[] = [
    ...rows.map(
      (job): HistoryEntry => ({
        kind: "job",
        at: job.createdAt,
        symbol: job.symbol,
        resolution: job.resolution,
        job,
      }),
    ),
    ...deletions.map(
      (deletion): HistoryEntry => ({
        kind: "deletion",
        at: deletion.deletedAt,
        symbol: deletion.symbol,
        resolution: deletion.resolution,
        deletion,
      }),
    ),
  ];
  // Newest first, whatever the instrument: this tab is asked "what just happened" before
  // anything else (terminal-collection-history spec, "Historia jest ułożona od
  // najnowszego zdarzenia"). The cost, taken deliberately, is that a deletion no longer
  // sits beside the pull it undid — that story can still be followed down the symbol
  // column, while "what just happened" had no workaround at all (design.md).
  //
  // Symbol and interval are the tiebreak because seconds collide — a wizard submission
  // stamps every pair with the same `at` — and the two lists come from independent
  // polls, so input order is no help even though the sort is stable.
  return entries.sort((a, b) => {
    if (a.at !== b.at) return b.at - a.at;
    if (a.symbol !== b.symbol) return a.symbol.localeCompare(b.symbol);
    return RESOLUTIONS.indexOf(a.resolution) - RESOLUTIONS.indexOf(b.resolution);
  });
}

export function CollectionHistoryView() {
  const history = useJobHistory(archive);
  const entries = useMemo(
    () => combinedEntries(history.rows, history.deletions),
    [history.rows, history.deletions],
  );
  // Which job is open, not a copy of it: the dialog is built from the rows
  // below on every render, so the ten-second poll refreshes what it shows
  // instead of leaving a snapshot ageing on screen.
  const [openJobId, setOpenJobId] = useState<number | null>(null);
  const openRows = useMemo(
    () => (openJobId === null ? [] : history.rows.filter((r) => r.jobId === openJobId)),
    [history.rows, openJobId],
  );

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 overflow-auto">
        <HistoryList history={history} entries={entries} onOpenJob={setOpenJobId} />
      </div>

      {openJobId !== null && openRows.length > 0 && (
        <JobDialog
          jobId={openJobId}
          rows={openRows}
          onChanged={history.reload}
          onClose={() => setOpenJobId(null)}
        />
      )}
    </div>
  );
}

function HistoryList({
  history,
  entries,
  onOpenJob,
}: {
  history: JobHistoryState;
  entries: HistoryEntry[];
  onOpenJob(jobId: number): void;
}) {
  if (history.status === "loading") {
    return <p className="px-4 py-6 text-sm text-ink-muted">Reading collection history…</p>;
  }

  // An empty list and an unanswered question are the same empty array, and
  // only one of them means nothing has ever been pulled.
  if (history.status === "unreachable") {
    return (
      <UnreachableNotice className="px-4 py-6 text-sm text-critical" onRetry={history.reload}>
        The archive is not reachable, so collection history is unknown — this is not an empty
        list. {history.error}
      </UnreachableNotice>
    );
  }

  return (
    <>
      {history.error && (
        // The rows below are the last good answer; saying so beats replacing
        // them with an error over one missed refresh.
        <p className="px-4 pt-3 text-xs text-warning">
          The last refresh failed ({history.error}); the rows below may be out of date.
        </p>
      )}

      {entries.length === 0 ? (
        <p className="px-4 py-6 text-sm text-ink-muted">
          Nothing has been collected yet. Add an instrument in the{" "}
          <Link to="/instruments" className="text-ink underline">
            Instruments
          </Link>{" "}
          tab to start.
        </p>
      ) : (
        <table className="w-full text-sm">
          <thead className="sticky top-0 border-b border-secondary-line bg-canvas text-left text-[11px] uppercase tracking-wide text-secondary">
            <tr>
              <th className="px-4 py-2 font-normal">Symbol</th>
              <th className="px-4 py-2 font-normal">Resolution</th>
              <th className="px-4 py-2 font-normal">When</th>
              <th className="px-4 py-2 font-normal">Status</th>
              <th className="px-4 py-2 font-normal">Progress</th>
              <th className="px-4 py-2 font-normal">Range</th>
              <th className="px-4 py-2 font-normal" />
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) =>
              entry.kind === "job" ? (
                <HistoryRow
                  key={`job|${entry.job.jobId}|${entry.symbol}|${entry.resolution}`}
                  row={entry.job}
                  onOpenJob={onOpenJob}
                />
              ) : (
                <DeletionRow
                  key={`deletion|${entry.symbol}|${entry.resolution}|${entry.at}`}
                  deletion={entry.deletion}
                />
              ),
            )}
          </tbody>
        </table>
      )}
    </>
  );
}

function HistoryRow({ row, onOpenJob }: { row: JobPairView; onOpenJob(jobId: number): void }) {
  const reasons = failureReasons(row.chunks);
  const range = chunkRange(row.chunks);
  const collected = collectedRange(row.chunks);
  // Only for a job that finished cleanly. A range still filling in is not a shortfall,
  // and a chunk that *failed* says nothing about what the provider holds — reading its
  // absence as "the history stops here" turns an outage into a claim about the
  // instrument. `succeeded` is exactly the case where every unfinished chunk was
  // skipped, which is the provider having answered.
  const whole = row.status === "succeeded" && range !== null;
  const shallow = whole && collected !== null && collected.start > range.start;
  const nothingReached = whole && collected === null;
  const pct = row.chunksTotal > 0 ? Math.round((row.chunksDone / row.chunksTotal) * 100) : 0;
  const explainsItself = row.status !== "running" && row.status !== "succeeded";

  // Only worth saying while something is supposed to be happening. On a job
  // that finished, "nothing since" is not news.
  const idleFor = row.status === "running" ? secondsSince(row.lastActivityAt) : null;
  const stalled = idleFor !== null && idleFor >= STALL_AFTER_SECONDS;

  return (
    <>
      <tr
        data-testid={`history-${row.jobId}-${row.symbol}-${row.resolution}`}
        data-stalled={stalled}
        onClick={() => onOpenJob(row.jobId)}
        className={`cursor-pointer border-t border-border hover:bg-panel ${
          stalled ? "border-l-2 border-l-warning" : ""
        }`}
      >
        <td className="px-4 py-1.5 font-semibold text-ink">{row.symbol}</td>
        <td className="px-4 py-1.5 text-ink-secondary">{RESOLUTION_LABEL[row.resolution]}</td>
        <td className="px-4 py-1.5 text-ink-muted">{formatInstant(row.createdAt)}</td>
        <td className="px-4 py-1.5">
          <span className={STATUS_CLASS[row.status]}>{STATUS_LABEL[row.status]}</span>
        </td>
        <td className="px-4 py-1.5 text-ink-secondary">
          {row.status === "running" ? (
            <>
              {pct}% ({row.chunksDone}/{row.chunksTotal} chunks) ·{" "}
              {row.candlesWritten.toLocaleString()} candles so far ·{" "}
              {/* The one number that tells work apart from a standstill: the two
                  read identically in every other column (terminal-collection-history
                  spec, "Praca w toku pokazuje mierzony postęp"). */}
              <span className={stalled ? "font-semibold text-warning" : undefined}>
                nothing for {elapsedLabel(idleFor ?? 0)}
              </span>
            </>
          ) : (
            <>{row.candlesWritten.toLocaleString()} candles</>
          )}
        </td>
        <td className="px-4 py-1.5 text-ink-secondary">
          {range ? `${formatInstant(range.start)} → ${formatInstant(range.end)}` : "—"}
          {shallow && collected && (
            <div className="text-xs text-warning">
              collected from {formatInstant(collected.start)}
            </div>
          )}
          {nothingReached && (
            <div className="text-xs text-warning">nothing in this range to collect</div>
          )}
        </td>
        <td className="px-4 py-1.5 text-right">
          {/* Where Retry used to sit. It retried the whole job from beside one
              pair, which is a promise the position contradicted; the job — every
              pair of it — is what the dialog behind this shows and retries
              (terminal-collection-history spec, "Ponowienie stoi przy całości,
              nie przy parze"). Keyboard-reachable in its own right, so opening a
              job never needs a pointer. */}
          <button
            type="button"
            aria-label={`Job ${row.jobId} details`}
            onClick={(e) => {
              e.stopPropagation();
              onOpenJob(row.jobId);
            }}
            className="rounded border border-border px-2 py-0.5 text-xs text-ink-muted hover:text-ink"
          >
            Job #{row.jobId}
          </button>
        </td>
      </tr>

      {explainsItself && (
        <tr className="border-t border-border">
          <td colSpan={7} className="px-4 py-1 text-xs text-critical">
            {reasons.length > 0 ? reasons.join("; ") : "no reason given"}
          </td>
        </tr>
      )}

    </>
  );
}

/**
 * One collection job, whole — the only place it is visible as one thing. The tab stays a
 * flat timeline because grouping by job would file the newest event wherever its job
 * happened to start, so the job is assembled here out of rows already on screen: no
 * second request, no second freshness clock, and it moves with the ten-second poll.
 *
 * Retry lives here because this is where its scope is visible — it re-runs every failed
 * chunk of every pair the job touched, which is what the per-row button used to do while
 * looking like it did less. Removing the job from the history is here for the same
 * reason, and the two share nothing else: one re-runs work, the other forgets it ever
 * happened without touching a candle.
 */
function JobDialog({
  jobId,
  rows,
  onChanged,
  onClose,
}: {
  jobId: number;
  rows: JobPairView[];
  onChanged(): void;
  onClose(): void;
}) {
  // The second question is a second dialog, not a second button beside "Retry job".
  // `ConfirmDialog` asks one thing and answers it once; two irreversible buttons on one
  // panel is how the wrong one gets pressed (`terminal-dialogs` spec, "Pytanie o zgodę
  // jest dialogiem").
  const [removing, setRemoving] = useState(false);
  const chunks = rows.flatMap((row) => row.chunks);
  const retryable = chunks.filter(
    (chunk) => chunk.state === "failed" || chunk.state === "interrupted",
  );
  const pairsWithFailures = rows.filter((row) =>
    row.chunks.some((chunk) => chunk.state === "failed" || chunk.state === "interrupted"),
  );
  const reasons = failureReasons(chunks);
  const running = rows.some((row) => row.status === "running");
  const lastActivity = Math.max(...rows.map((row) => row.lastActivityAt));
  const candlesCollected = rows.reduce((total, row) => total + row.candlesWritten, 0);

  const retry = useCallback(async () => {
    await archive.retryJob(jobId, new AbortController().signal);
    onChanged();
  }, [jobId, onChanged]);

  const remove = useCallback(async () => {
    await archive.deleteJob(jobId, new AbortController().signal);
    onChanged();
    // Closed from here rather than by `closeOnSuccess`, whose `onClose` is the way back
    // to the job dialog — and the job it shows no longer exists.
    onClose();
  }, [jobId, onChanged, onClose]);

  const body = (
    <>
      <p className="mt-3 text-ink-secondary">
        {rows.length} pair{rows.length === 1 ? "" : "s"}, started {formatInstant(rows[0].createdAt)}
        {rows[0].attempt > 1 && ` · attempt ${rows[0].attempt}`}
        {running && ` · nothing for ${elapsedLabel(secondsSince(lastActivity))}`}
      </p>

      <table className="mt-3 w-full text-xs">
        <thead className="text-left text-ink-muted">
          <tr>
            <th className="px-2 py-1 font-normal">Symbol</th>
            <th className="px-2 py-1 font-normal">Resolution</th>
            <th className="px-2 py-1 font-normal">Status</th>
            <th className="px-2 py-1 font-normal">Chunks</th>
            <th className="px-2 py-1 text-right font-normal">Candles</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.symbol}|${row.resolution}`} className="border-t border-border">
              <td className="px-2 py-1.5 font-semibold text-ink">{row.symbol}</td>
              <td className="px-2 py-1.5 text-ink-secondary">{RESOLUTION_LABEL[row.resolution]}</td>
              <td className="px-2 py-1.5">
                <span className={STATUS_CLASS[row.status]}>{STATUS_LABEL[row.status]}</span>
              </td>
              <td className="px-2 py-1.5 text-ink-secondary">
                {row.chunksDone}/{row.chunksTotal}
              </td>
              <td className="px-2 py-1.5 text-right text-ink-secondary">
                {row.candlesWritten.toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {reasons.length > 0 && (
        <div className="mt-3">
          <p className="text-critical">Why chunks failed:</p>
          <ul className="mt-1 list-disc pl-5 text-critical">
            {reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      )}

      {retryable.length > 0 && (
        // Said in full before it is done, because the scope is the whole point:
        // this is the job, not the row the operator opened it from.
        <p className="mt-3 text-ink">
          Retrying re-runs {retryable.length} failed chunk{retryable.length === 1 ? "" : "s"} across{" "}
          {pairsWithFailures.length} pair{pairsWithFailures.length === 1 ? "" : "s"}. Chunks already
          collected are left alone.
        </p>
      )}

      {running ? (
        // The archive refuses this outright, so offering it and reporting the refusal
        // afterwards would be asking a question whose answer is already known.
        <p className="mt-3 text-ink-muted">
          This job cannot be removed from the history while its chunks are still running.
        </p>
      ) : (
        <button
          type="button"
          onClick={() => setRemoving(true)}
          className="mt-3 rounded border border-border px-2 py-0.5 text-xs text-ink-muted hover:text-ink"
        >
          Remove from history
        </button>
      )}
    </>
  );

  if (removing) {
    return (
      <ConfirmDialog
        title={`Remove job #${jobId} from the history`}
        confirmLabel="Remove"
        busyLabel="Removing…"
        tone="danger"
        fallbackError="could not remove the job from the history"
        closeOnSuccess={false}
        onConfirm={remove}
        onClose={() => setRemoving(false)}
      >
        <p className="mt-3 text-ink">
          Removes this pull from the history — {rows.length} pair{rows.length === 1 ? "" : "s"} and{" "}
          {chunks.length} chunk{chunks.length === 1 ? "" : "s"}.
        </p>
        {/* The one sentence that separates this from deleting a pair's data, which is
            the other irreversible thing in this terminal with a similar name
            (terminal-collection-history spec, "Wpis dociągnięcia da się usunąć"). */}
        <p className="mt-2 text-ink-secondary">
          The {candlesCollected.toLocaleString()} candles it collected stay in the archive. This
          removes the record of the pull, not the data.
        </p>
      </ConfirmDialog>
    );
  }

  if (retryable.length === 0) {
    return (
      <ConfirmDialog
        title={`Collection job #${jobId}`}
        confirmLabel="Close"
        busyLabel="Close"
        cancelLabel={null}
        onConfirm={() => {}}
        onClose={onClose}
      >
        {body}
      </ConfirmDialog>
    );
  }

  return (
    <ConfirmDialog
      title={`Collection job #${jobId}`}
      confirmLabel="Retry job"
      busyLabel="Retrying…"
      fallbackError="could not queue the retry"
      onConfirm={retry}
      onClose={onClose}
    >
      {body}
    </ConfirmDialog>
  );
}

/**
 * A skasowanie, in the same table a pull's row lives in — deliberately not
 * styled like one. It is neither a success nor a failure, so it MUST NOT
 * borrow `text-good` (reserved for a job that succeeded) or `text-critical`
 * (a job that failed): reading it at a glance has to say "something was
 * removed", not "something went wrong" or "something finished".
 */
function DeletionRow({ deletion }: { deletion: PairDeletion }) {
  const { removedFrom, removedTo } = deletion;
  return (
    <tr
      data-testid={`deletion-${deletion.symbol}-${deletion.resolution}-${deletion.deletedAt}`}
      className="border-t border-border"
    >
      <td className="px-4 py-1.5 font-semibold text-ink">{deletion.symbol}</td>
      <td className="px-4 py-1.5 text-ink-secondary">{RESOLUTION_LABEL[deletion.resolution]}</td>
      <td className="px-4 py-1.5 text-ink-muted">{formatInstant(deletion.deletedAt)}</td>
      <td className="px-4 py-1.5">
        <span className="font-semibold text-ink-secondary">deleted</span>
      </td>
      <td className="px-4 py-1.5 text-ink-secondary">
        −{deletion.candlesRemoved.toLocaleString()} candles
      </td>
      <td className="px-4 py-1.5 text-ink-secondary">
        {removedFrom !== null && removedTo !== null
          ? `${formatInstant(removedFrom)} → ${formatInstant(removedTo)}`
          : "—"}
      </td>
      <td className="px-4 py-1.5" />
    </tr>
  );
}
