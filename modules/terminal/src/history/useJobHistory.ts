import { useCallback, useEffect, useState } from "react";
import type { ArchiveAdmin } from "../data/source";
import type { JobPairView } from "../data/types";

/** How often the tab re-asks, while it is open (`terminal-collection-history`
 *  spec, "Zakładka odświeża się sama"). */
const POLL_MS = 30_000;

export type JobHistoryStatus = "loading" | "ready" | "unreachable";

export interface JobHistoryState {
  status: JobHistoryStatus;
  /** Every job, one row per pair it touched, newest job first. */
  rows: JobPairView[];
  /** Why the last poll failed. Never blanks `rows` on its own — the rows
   *  already on screen are the last good answer. */
  error: string | null;
  reload(): void;
}

/**
 * What has been pulled, kept current — the same shape of state as
 * `useTrackedPairs`, for the same reason: a failed poll must not blank rows
 * that are already on screen, and "nothing has run yet" must read
 * differently from "nobody could be asked" (terminal-collection-history spec,
 * "Zakładka odróżnia brak historii od braku odpowiedzi").
 */
export function useJobHistory(admin: ArchiveAdmin): JobHistoryState {
  const [rows, setRows] = useState<JobPairView[]>([]);
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
      admin
        .listJobs(null, null, controller.signal)
        .then((next) => {
          if (cancelled) return;
          setRows(next);
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

  return { status, rows, error, reload };
}
