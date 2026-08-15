import { useEffect, useRef, useState } from "react";
import type { IndicatorSource } from "../../data/source";
import type { IndicatorResult, IndicatorSelection, Resolution } from "../../data/types";

export type IndicatorsStatus = "idle" | "loading" | "ready" | "error";

export interface IndicatorsState {
  status: IndicatorsStatus;
  times: number[];
  results: IndicatorResult[];
  /** The selections these results were computed for, in the order they were asked for —
   *  `results[i]` answers `selections[i]` (`market-data-indicators` spec, "Kolejność
   *  wyników"). Kept beside the results rather than read from the caller's current
   *  state: while a read is in flight the operator may already have added an instance,
   *  and zipping fresh selections onto stale results would mislabel every one of them. */
  selections: IndicatorSelection[];
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
  selections: [],
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

  // What actually changes the answer: which instances were asked for, and with what
  // params. Colour is deliberately not in here — picking a swatch repaints a line the
  // chart already holds, and refetching the archive for it would make choosing a colour
  // cost a read (design.md, "Kolor rozwiązywany przy rysowaniu").
  const specsKey = selections
    .map((s) => `${s.key}|${s.id}|${JSON.stringify(s.params)}`)
    .join(";");
  const selectionsRef = useRef(selections);
  selectionsRef.current = selections;

  useEffect(() => {
    const selections = selectionsRef.current;
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
          selections,
          error: null,
          retry: () => setAttempt((n) => n + 1),
        });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        // The last good answer stays on screen, and it keeps the selections it was
        // computed for: the two are one snapshot, and carrying half of it forward is
        // exactly the mislabelling this field exists to prevent.
        setState((prev) => ({
          status: "error",
          times: prev.times,
          results: prev.results,
          selections: prev.selections,
          error: err instanceof Error ? err.message : "could not compute the selected indicators",
          retry: () => setAttempt((n) => n + 1),
        }));
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
    // `range` relies on the caller keeping the reference stable across renders — a
    // `useState` setter called only when the value actually changes, which `Chart.tsx`
    // already does. Selections come in through `specsKey` instead, so a change that
    // cannot alter the answer does not cost a read.
  }, [source, symbol, resolution, range, specsKey, attempt]);

  return state;
}
