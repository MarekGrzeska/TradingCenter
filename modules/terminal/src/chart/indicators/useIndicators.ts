import { useEffect, useState } from "react";
import type { IndicatorSource } from "../../data/source";
import type { IndicatorResult, IndicatorSelection, Resolution } from "../../data/types";

export type IndicatorsStatus = "idle" | "loading" | "ready" | "error";

export interface IndicatorsState {
  status: IndicatorsStatus;
  times: number[];
  results: IndicatorResult[];
  error: string | null;
  retry(): void;
}

export interface BarsRange {
  from: number;
  to: number;
}

const IDLE: IndicatorsState = {
  status: "idle",
  times: [],
  results: [],
  error: null,
  retry: () => {},
};

/**
 * Computes the operator's chosen indicators over whatever range the chart currently has
 * candles for — recomputed when that range changes structurally (a new symbol, a new
 * resolution, older history paged in), not on every live tick. Chasing the forming
 * candle is `docs/wskazniki-plan-wdrozenia.html`'s stage 5 ("na żywo"), not this one: an
 * indicator here holds its last computed value until the next structural change.
 *
 * A failed compute never touches what candles are on screen — `market-data-indicators`
 * spec has no requirement to that effect because it is a terminal concern, not an
 * archive one, but `terminal-chart`'s "Wykres mówi, gdy wskaźników nie da się policzyć"
 * is exactly this: the caller shows candles regardless of `status`.
 */
export function useIndicators(
  source: IndicatorSource | undefined,
  symbol: string,
  resolution: Resolution,
  selections: IndicatorSelection[],
  range: BarsRange | null,
): IndicatorsState {
  const [state, setState] = useState<IndicatorsState>(IDLE);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!source || selections.length === 0 || range === null) {
      setState(IDLE);
      return;
    }

    let cancelled = false;
    const controller = new AbortController();
    setState((prev) => ({ ...prev, status: "loading", error: null }));

    source
      .computeIndicators(symbol, resolution, range.from, range.to, selections, controller.signal)
      .then((computed) => {
        if (cancelled) return;
        setState({
          status: "ready",
          times: computed.times,
          results: computed.results,
          error: null,
          retry: () => setAttempt((n) => n + 1),
        });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setState((prev) => ({
          status: "error",
          times: prev.times,
          results: prev.results,
          error: err instanceof Error ? err.message : "could not compute the selected indicators",
          retry: () => setAttempt((n) => n + 1),
        }));
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
    // `range` and `selections` both rely on the caller keeping the reference stable
    // across renders — a `useState` setter called only when the value actually
    // changes, which `Chart.tsx` already does for both.
  }, [source, symbol, resolution, range, selections, attempt]);

  return state;
}
