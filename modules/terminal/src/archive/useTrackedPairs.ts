import { useCallback, useEffect, useState } from "react";
import type { ArchiveAdmin } from "../data/source";
import type { TrackedPair } from "../data/types";

/** How often the list re-asks. Collection state is the reason: a subscription
 *  can die without a sound, and a panel that only refreshed on demand would
 *  show a pair as healthy for as long as nobody thought to look again. */
const POLL_MS = 15_000;

export type PairsStatus = "loading" | "ready" | "unreachable";

export interface TrackedPairsState {
  status: PairsStatus;
  pairs: TrackedPair[];
  /** Why the list could not be read. Never a raw transport error. */
  error: string | null;
  reload(): void;
}

/**
 * What the archive is collecting, kept current.
 *
 * `status` separates "nothing is being archived" from "nobody could be asked" —
 * the two look identical as an empty array, and only one of them means the
 * operator has nothing set up (terminal-data-manager spec, "Panel mówi, gdy
 * archiwum nie odpowiada").
 *
 * A failed poll does not blank a list that is already on screen: the pairs
 * shown stay, and the failure is reported beside them. Replacing real rows with
 * an error because one refresh out of many missed would be a worse answer than
 * slightly stale rows.
 */
export function useTrackedPairs(admin: ArchiveAdmin): TrackedPairsState {
  const [pairs, setPairs] = useState<TrackedPair[]>([]);
  const [status, setStatus] = useState<PairsStatus>("loading");
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
        .listPairs(controller.signal)
        .then((next) => {
          if (cancelled) return;
          setPairs(next);
          setStatus("ready");
          setError(null);
        })
        .catch((cause: unknown) => {
          if (cancelled || controller.signal.aborted) return;
          setError(cause instanceof Error ? cause.message : "could not read the archive");
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

  return { status, pairs, error, reload };
}
