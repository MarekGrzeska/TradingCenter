import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router";
import { archive } from "../data/marketData";
import { RESOLUTIONS } from "../data/types";
import type { Chunk, JobPairView, JobStatus } from "../data/types";
import { formatInstant } from "../instruments/format";
import { useJobHistory } from "./useJobHistory";
import type { JobHistoryState } from "./useJobHistory";

/**
 * Every pull the archive has run, per instrument and per interval — the
 * question `market-data-jobs` exists to answer without a log: what got
 * dociągnięte, how far a running one has got, and where to retry what
 * failed without touching the pair's archived status at all.
 */

const STATUS_LABEL: Record<JobStatus, string> = {
  running: "running",
  succeeded: "done",
  partial: "partial",
  failed: "failed",
  interrupted: "interrupted",
};

const STATUS_CLASS: Record<JobStatus, string> = {
  running: "text-ink-secondary",
  succeeded: "font-semibold text-up",
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

function sortRows(rows: JobPairView[]): JobPairView[] {
  // Symbol, then interval in its own canonical order, then newest attempt
  // first within the same pair — never only the latest, as if earlier pulls
  // never happened (terminal-collection-history spec, "Wiele dociągnięć tej
  // samej pary").
  return [...rows].sort((a, b) => {
    if (a.symbol !== b.symbol) return a.symbol.localeCompare(b.symbol);
    const byResolution = RESOLUTIONS.indexOf(a.resolution) - RESOLUTIONS.indexOf(b.resolution);
    if (byResolution !== 0) return byResolution;
    return b.createdAt - a.createdAt;
  });
}

export function CollectionHistoryView() {
  const history = useJobHistory(archive);
  const rows = useMemo(() => sortRows(history.rows), [history.rows]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 overflow-auto">
        <HistoryList history={history} rows={rows} />
      </div>
    </div>
  );
}

function HistoryList({ history, rows }: { history: JobHistoryState; rows: JobPairView[] }) {
  if (history.status === "loading") {
    return <p className="px-4 py-6 text-sm text-ink-muted">Reading collection history…</p>;
  }

  // An empty list and an unanswered question are the same empty array, and
  // only one of them means nothing has ever been pulled.
  if (history.status === "unreachable") {
    return (
      <p className="px-4 py-6 text-sm text-critical">
        The archive is not reachable, so collection history is unknown — this is not an empty
        list. {history.error}
        <button
          type="button"
          onClick={history.reload}
          className="ml-3 rounded border border-border px-2 py-0.5 text-xs text-ink hover:bg-panel-strong"
        >
          Retry
        </button>
      </p>
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

      {rows.length === 0 ? (
        <p className="px-4 py-6 text-sm text-ink-muted">
          Nothing has been collected yet. Add an instrument in the{" "}
          <Link to="/instruments" className="text-ink underline">
            Instruments
          </Link>{" "}
          tab to start.
        </p>
      ) : (
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-canvas text-left text-xs text-ink-muted">
            <tr>
              <th className="px-4 py-2 font-normal">Symbol</th>
              <th className="px-4 py-2 font-normal">Resolution</th>
              <th className="px-4 py-2 font-normal">Started</th>
              <th className="px-4 py-2 font-normal">Status</th>
              <th className="px-4 py-2 font-normal">Progress</th>
              <th className="px-4 py-2 font-normal">Range</th>
              <th className="px-4 py-2 font-normal" />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <HistoryRow
                key={`${row.jobId}|${row.symbol}|${row.resolution}`}
                row={row}
                onChanged={history.reload}
              />
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

function HistoryRow({ row, onChanged }: { row: JobPairView; onChanged(): void }) {
  const [confirming, setConfirming] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);

  const retryableChunks = row.chunks.filter(
    (chunk) => chunk.state === "failed" || chunk.state === "interrupted",
  );
  const reasons = failureReasons(row.chunks);
  const range = chunkRange(row.chunks);
  const pct = row.chunksTotal > 0 ? Math.round((row.chunksDone / row.chunksTotal) * 100) : 0;
  const explainsItself = row.status !== "running" && row.status !== "succeeded";

  const retry = useCallback(async () => {
    setRetryError(null);
    setRetrying(true);
    try {
      await archive.retryJob(row.jobId, new AbortController().signal);
      setConfirming(false);
      onChanged();
    } catch (cause: unknown) {
      // A retry request that itself fails must not read as a retry that
      // started — the row stays exactly as it was (terminal-collection-history
      // spec, "Ponowienie samo zawodzi").
      setRetryError(cause instanceof Error ? cause.message : "could not queue the retry");
    } finally {
      setRetrying(false);
    }
  }, [row.jobId, onChanged]);

  return (
    <>
      <tr
        data-testid={`history-${row.jobId}-${row.symbol}-${row.resolution}`}
        className="border-t border-border"
      >
        <td className="px-4 py-1.5 font-semibold text-ink">{row.symbol}</td>
        <td className="px-4 py-1.5 text-ink-secondary">{row.resolution}</td>
        <td className="px-4 py-1.5 text-ink-muted">{formatInstant(row.createdAt)}</td>
        <td className="px-4 py-1.5">
          <span className={STATUS_CLASS[row.status]}>{STATUS_LABEL[row.status]}</span>
        </td>
        <td className="px-4 py-1.5 text-ink-secondary">
          {row.status === "running" ? (
            <>
              {pct}% ({row.chunksDone}/{row.chunksTotal} chunks) ·{" "}
              {row.candlesWritten.toLocaleString()} candles so far
            </>
          ) : (
            <>{row.candlesWritten.toLocaleString()} candles</>
          )}
        </td>
        <td className="px-4 py-1.5 text-ink-secondary">
          {range ? `${formatInstant(range.start)} → ${formatInstant(range.end)}` : "—"}
        </td>
        <td className="px-4 py-1.5 text-right">
          {retryableChunks.length > 0 && (
            <button
              type="button"
              aria-label={`Retry ${row.symbol} ${row.resolution}`}
              onClick={() => setConfirming(true)}
              className="rounded border border-border px-2 py-0.5 text-xs text-ink-muted hover:text-ink"
            >
              Retry
            </button>
          )}
        </td>
      </tr>

      {explainsItself && (
        <tr className="border-t border-border">
          <td colSpan={7} className="px-4 py-1 text-xs text-critical">
            {reasons.length > 0 ? reasons.join("; ") : "no reason given"}
          </td>
        </tr>
      )}

      {confirming && (
        <tr className="border-t border-border bg-panel">
          <td colSpan={7} className="px-4 py-2">
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <span className="text-ink">
                Retry {retryableChunks.length} chunk{retryableChunks.length === 1 ? "" : "s"} for{" "}
                {row.symbol} {row.resolution}?
              </span>
              <button
                type="button"
                disabled={retrying}
                onClick={retry}
                className="rounded border border-accent px-2 py-0.5 text-xs text-ink hover:bg-panel-strong disabled:opacity-50"
              >
                {retrying ? "Retrying…" : "Retry"}
              </button>
              <button
                type="button"
                onClick={() => setConfirming(false)}
                className="rounded border border-border px-2 py-0.5 text-xs text-ink-muted hover:text-ink"
              >
                Cancel
              </button>
              {retryError && <span className="text-critical">{retryError}</span>}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
