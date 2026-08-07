import { useEffect, useState } from "react";
import type { MarketDataSource } from "../data/source";

export type SourceHealth = "checking" | "reachable" | "unreachable";

const POLL_MS = 15_000;

/** Pings `source` on mount, on every source change, and every `POLL_MS` after
 *  — independent of whatever charts are or aren't subscribed, so the
 *  indicator in the top bar reflects the source itself, not one chart's luck.
 *  terminal-shell spec, "Stan źródła danych jest widoczny globalnie". */
export function useSourceHealth(source: MarketDataSource): SourceHealth {
  const [health, setHealth] = useState<SourceHealth>("checking");

  useEffect(() => {
    let cancelled = false;
    let inFlight: AbortController | null = null;
    setHealth("checking");

    function check() {
      inFlight?.abort();
      const controller = new AbortController();
      inFlight = controller;
      source
        .ping(controller.signal)
        .then(() => {
          if (!cancelled) setHealth("reachable");
        })
        .catch(() => {
          if (!cancelled) setHealth("unreachable");
        });
    }

    check();
    const interval = setInterval(check, POLL_MS);

    return () => {
      cancelled = true;
      inFlight?.abort();
      clearInterval(interval);
    };
  }, [source]);

  return health;
}
