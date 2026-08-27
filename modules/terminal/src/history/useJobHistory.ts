import { useRead } from "../data/query";
import type { ArchiveAdmin } from "../data/source";
import type { JobPairView, PairDeletion } from "../data/types";

/** How often the tab re-asks while open. Ten seconds, not the thirty this started at: the read costs one query to the
 *  archive's own database, and a `MINUTE` chunk settles fast enough that thirty made a working job look stalled. */
const POLL_MS = 10_000;

interface Both {
  rows: JobPairView[];
  deletions: PairDeletion[];
}

/** Rendered until the first answer — one identity, not a pair of fresh arrays per render. */
const NONE: Both = { rows: [], deletions: [] };

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
 * What has been pulled and what has been deleted, kept current. One query over both rather than two: "jobs refreshed,
 * deletions did not" is not a state worth telling apart from a failed poll — one cache entry, one status.
 */
export function useJobHistory(admin: ArchiveAdmin): JobHistoryState {
  const read = useRead<Both>({
    key: ["archive", "collection-history"],
    read: async (signal) => {
      const [rows, deletions] = await Promise.all([
        admin.listJobs(null, null, signal),
        admin.listDeletions(null, null, signal),
      ]);
      return { rows, deletions };
    },
    initial: NONE,
    fallbackMessage: "could not read collection history",
    pollMs: POLL_MS,
  });

  return {
    status: read.status === "error" ? "unreachable" : read.status,
    rows: read.value.rows,
    deletions: read.value.deletions,
    error: read.error,
    reload: read.reload,
  };
}
