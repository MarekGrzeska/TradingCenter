import { useCallback, useEffect, useState } from "react";
import type { ArchiveAdmin } from "../data/source";
import type { JobPairView, PairDeletion } from "../data/types";

/** How often the tab re-asks, while it is open (`terminal-collection-history`
 *  spec, "Zakładka odświeża się sama").
 *
 *  Ten seconds, not the thirty this started at. The read costs one query to the
 *  archive's own database — never the gateway, so it cannot eat into the
 *  provider budget the chunks themselves are queued behind — and a `MINUTE`
 *  chunk settles every few tens of seconds, so thirty was slow enough to make a
 *  working job look stalled. */
const POLL_MS = 10_000;

export type JobHistoryStatus = "loading" | "ready" | "unreachable";

export interface JobHistoryState {
  status: JobHistoryStatus;
  /** Every job, one row per pair it touched, newest job first. */
  rows: JobPairView[];
  /** Every recorded skasowanie, newest first — the other half of one
   *  instrument's history, read alongside `rows` rather than on demand, so
   *  the combined timeline the view builds never waits on two separate
   *  loading states. */
  deletions: PairDeletion[];
  /** Why the last poll failed. Never blanks `rows`/`deletions` on their own —
   *  what is already on screen is the last good answer. */
  error: string | null;
  reload(): void;
}

/**
 * What has been pulled and what has been deleted, kept current — the same
 * shape of state as `useTrackedPairs`, for the same reason: a failed poll
 * must not blank rows that are already on screen, and "nothing has run yet"
 * must read differently from "nobody could be asked" (terminal-collection-history
 * spec, "Zakładka odróżnia brak historii od braku odpowiedzi").
 *
 * The two reads are treated as one unit: either both land or neither does.
 * A deletion cutting a pair's history short is exactly the kind of thing an
 * operator reading this tab needs to see reliably, so there is no version of
 * "jobs refreshed, deletions did not" worth distinguishing from a plain
 * failed poll.
 */
export function useJobHistory(admin: ArchiveAdmin): JobHistoryState {
  const [rows, setRows] = useState<JobPairView[]>([]);
  const [deletions, setDeletions] = useState<PairDeletion[]>([]);
  const [status, setStatus] = useState<JobHistoryStatus>("loading");
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    let inFlight: AbortController | null = null;

    function read() {
      inFlight?.abort();
      const controller = new AbortController();
      inFlight = controller;
      Promise.all([
        admin.listJobs(null, null, controller.signal),
        admin.listDeletions(null, null, controller.signal),
      ])
        .then(([nextRows, nextDeletions]) => {
          if (cancelled) return;
          setRows(nextRows);
          setDeletions(nextDeletions);
          setStatus("ready");
          setError(null);
        })
        .catch((cause: unknown) => {
          if (cancelled || controller.signal.aborted) return;
          setError(cause instanceof Error ? cause.message : "could not read collection history");
          setStatus((current) => (current === "ready" ? "ready" : "unreachable"));
        });
    }

    read();
    const interval = setInterval(read, POLL_MS);

    return () => {
      cancelled = true;
      inFlight?.abort();
      clearInterval(interval);
    };
  }, [admin, attempt]);

  return { status, rows, deletions, error, reload };
}
