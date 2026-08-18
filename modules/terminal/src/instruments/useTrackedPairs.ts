import { useRead } from "../data/query";
import type { ArchiveAdmin } from "../data/source";
import type { TrackedPair } from "../data/types";

/** How often the list re-asks. Collection state is the reason: a subscription
 *  can die without a sound, and a panel that only refreshed on demand would
 *  show a pair as healthy for as long as nobody thought to look again. */
const POLL_MS = 15_000;

/** Rendered until the first answer. A module-level constant, so "no pairs yet"
 *  is one identity rather than a new array per render. */
const NONE: TrackedPair[] = [];

export type PairsStatus = "loading" | "ready" | "unreachable";

export interface TrackedPairsState {
  status: PairsStatus;
  pairs: TrackedPair[];
  /** Why the list could not be read. Never a raw transport error. */
  error: string | null;
  reload(): void;
}

/**
 * What the archive is collecting, kept current. `status` separates "nothing is being
 * archived" from "nobody could be asked" — both are an empty array, and only one means
 * the operator has nothing set up (terminal-data-manager spec, "Panel mówi, gdy archiwum
 * nie odpowiada").
 *
 * A failed poll does not blank rows already on screen; the failure is reported beside
 * them. Slightly stale rows beat an error where real data was. Both properties are
 * `useRead`'s now, shared with every other read in the terminal.
 */
export function useTrackedPairs(admin: ArchiveAdmin): TrackedPairsState {
  const read = useRead<TrackedPair[]>({
    key: ["archive", "pairs"],
    read: (signal) => admin.listPairs(signal),
    initial: NONE,
    fallbackMessage: "could not read the archive",
    pollMs: POLL_MS,
  });

  return {
    status: read.status === "error" ? "unreachable" : read.status,
    pairs: read.value,
    error: read.error,
    reload: read.reload,
  };
}
