import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { RefObject } from "react";
import type { IChartApi } from "lightweight-charts";
import type { IndicatorSource } from "../data/source";
import type { Bar, IndicatorSelection, Resolution } from "../data/types";
import { showToast } from "../ui/toastStore";
import { readChartColors, type ChartColors } from "./theme";
import { assignLineColors, drawnInstances } from "./chartLines";
import { indicatorWindow, windowStillCovers } from "./chartWindow";
import {
  type BarsRange,
  type IndicatorsState,
  useIndicators,
} from "./indicators/useIndicators";
import {
  useIndicatorCatalogue,
  type IndicatorCatalogueState,
} from "./indicators/useIndicatorCatalogue";
import type { IndicatorCatalogueEntry } from "../data/types";

/** Asked for while the catalogue has not answered yet — one identity, so waiting for it
 *  costs no render of its own. */
const NO_SELECTIONS: IndicatorSelection[] = [];

export interface ChartIndicatorsInput {
  indicatorSource: IndicatorSource | undefined;
  symbol: string;
  resolution: Resolution;
  initialIndicatorSelections: IndicatorSelection[] | undefined;
  onIndicatorSelectionsChange: ((next: IndicatorSelection[]) => void) | undefined;
  /** The chart's own two refs, read rather than written: the window is whatever the time
   *  scale is showing over whatever the series holds, and both move without a render. */
  chartRef: RefObject<IChartApi | null>;
  barsRef: RefObject<Bar[]>;
  colorsRef: RefObject<ChartColors | null>;
}

export interface ChartIndicators {
  indicatorSelections: IndicatorSelection[];
  setIndicatorSelections: (next: IndicatorSelection[]) => void;
  catalogue: IndicatorCatalogueState;
  catalogueById: Map<string, IndicatorCatalogueEntry>;
  knownIndicatorSelections: IndicatorSelection[];
  unknownIndicatorIds: string[];
  indicatorsState: IndicatorsState;
  instanceColors: Map<string, string | null>;
  /** Shaped by the two functions that build it rather than restated here — the readout
   *  and the layers have to be given exactly what `assignLineColors` returns. */
  readoutAssignment: {
    drawn: ReturnType<typeof drawnInstances>;
    lineColors: ReturnType<typeof assignLineColors>;
  };
  failedIndicators: IndicatorsState["results"];
  failureDigest: string;
  /** Called from the chart's own handlers — a pan, a candle closing, a page of history
   *  landing — which run outside React, so the function has to be reachable through a ref
   *  that is always the current one. */
  syncIndicatorWindowRef: RefObject<(force?: boolean) => void>;
  /** What a symbol, resolution or source change owes the indicators: with no window there
   *  are no results, which the layer sync reads as "remove every line". */
  clearIndicatorWindow: () => void;
}

/**
 * The operator's chosen indicators, from the picker to the numbers a line is drawn from:
 * which ones the catalogue still offers, over which window they are computed, what colour
 * each instance carries, and what to say when one of them cannot be had.
 *
 * Split out of `Chart.tsx` because it is the half of that file with a boundary of its own:
 * the chart's lifecycle writes candles into a canvas, and this reads what the canvas is
 * showing and asks the archive about it. The two meet at four places and no more — the two
 * refs handed in, the window sync the chart's handlers call, and the state the layers draw.
 */
export function useChartIndicators({
  indicatorSource,
  symbol,
  resolution,
  initialIndicatorSelections,
  onIndicatorSelectionsChange,
  chartRef,
  barsRef,
  colorsRef,
}: ChartIndicatorsInput): ChartIndicators {
  const [indicatorSelections, setIndicatorSelectionsState] = useState<IndicatorSelection[]>(
    () => initialIndicatorSelections ?? [],
  );
  // A ref, not a dependency: notifying the caller must not itself be a reason
  // to redo anything below, only a side effect of the operator's own action.
  const onIndicatorSelectionsChangeRef = useRef(onIndicatorSelectionsChange);
  onIndicatorSelectionsChangeRef.current = onIndicatorSelectionsChange;
  const setIndicatorSelections = useCallback((next: IndicatorSelection[]) => {
    setIndicatorSelectionsState(next);
    onIndicatorSelectionsChangeRef.current?.(next);
  }, []);
  // The lazy `useState` initializer above only ever runs once, at mount — a later change
  // to the prop is otherwise invisible until the component remounts (a page reload,
  // previously the only way an agent-set indicator ever appeared). Re-adopted here
  // whenever the prop is a *different* array than the one already in state: the
  // operator's own edit above already set that state before its callback reaches the
  // grid store, so the round-tripped prop is the same reference and this is a no-op for
  // it; a write from elsewhere — `chartControl.ts`'s `syncAgentChart`, so far the one
  // other writer of a slot's indicators — hands back a new one and belongs on screen
  // without the operator refreshing to see it.
  useEffect(() => {
    if (initialIndicatorSelections === undefined) return;
    setIndicatorSelectionsState((current) =>
      current === initialIndicatorSelections ? current : initialIndicatorSelections,
    );
  }, [initialIndicatorSelections]);
  // The range indicators are computed over — set from what `redraw` actually drew, not
  // from every live tick, so an indicator does not refetch on each forming-candle update
  // (design.md's "na żywo" is a later stage; see `useIndicators`).
  const [barsRange, setBarsRange] = useState<BarsRange | null>(null);
  // What was last asked for, so a pan inside it costs nothing. State cannot answer this:
  // the range handler runs on every frame the library reports, long before a render.
  const heldIndicatorWindowRef = useRef<BarsRange | null>(null);

  /** Points the indicator window at what is on screen now, if what is on screen has left
   *  the window already computed. `force` for the structural changes that invalidate an
   *  answer whatever the frame is doing: a new period at the live edge, a series that
   *  just grew at the front. */
  const syncIndicatorWindow = useCallback(
    (force = false) => {
      const series = barsRef.current;
      const visible = chartRef.current?.timeScale().getVisibleLogicalRange() ?? null;
      const held = heldIndicatorWindowRef.current;
      if (!force && held !== null && windowStillCovers(held, series, visible)) return;
      // A forced sync always hands over a fresh object, even for an unchanged window, and
      // that is load-bearing rather than sloppy: `useIndicators` watches `range` by
      // reference, and a candle closing has to be recomputed over exactly the window that
      // was already asked for. Equal values, different answer.
      const next = indicatorWindow(series, visible, resolution);
      heldIndicatorWindowRef.current = next;
      setBarsRange(next);
    },
    [resolution, chartRef, barsRef],
  );
  const syncIndicatorWindowRef = useRef(syncIndicatorWindow);
  syncIndicatorWindowRef.current = syncIndicatorWindow;

  const catalogue = useIndicatorCatalogue(indicatorSource);
  const catalogueById = useMemo(
    () => new Map(catalogue.entries.map((entry) => [entry.id, entry] as const)),
    [catalogue.entries],
  );
  // A selection restored from a saved slot may name an indicator the catalogue no
  // longer offers (a removed entry, or storage from a build that had a
  // different one). Dropped from what actually computes and draws — surfaced
  // in the header instead — but never rewritten in the caller's storage on its
  // own: only an explicit change through the picker does that (terminal-grid
  // spec, "wpis nieznany katalogowi pomijany z komunikatem").
  //
  // The two not-ready states are not the same state. Still loading: nothing is asked
  // for yet, because a compute for an id the catalogue no longer offers is a read the
  // archive refuses, and the answer that would have filtered it is one tick away.
  // Failed: the selections pass through unfiltered, so a flaky read never reads as
  // "the archive removed everything".
  const { knownIndicatorSelections, unknownIndicatorIds } = useMemo(() => {
    if (catalogue.status === "loading") {
      return { knownIndicatorSelections: NO_SELECTIONS, unknownIndicatorIds: [] as string[] };
    }
    if (catalogue.status === "error") {
      return { knownIndicatorSelections: indicatorSelections, unknownIndicatorIds: [] as string[] };
    }
    const known: IndicatorSelection[] = [];
    const unknown: string[] = [];
    for (const selection of indicatorSelections) {
      if (catalogueById.has(selection.id)) known.push(selection);
      else unknown.push(selection.id);
    }
    return { knownIndicatorSelections: known, unknownIndicatorIds: unknown };
  }, [indicatorSelections, catalogue.status, catalogueById]);

  const indicatorsState = useIndicators(
    indicatorSource,
    symbol,
    resolution,
    knownIndicatorSelections,
    barsRange,
  );

  // The colours as they stand *now*, not as they stood when the archive last answered.
  // Picking a swatch must repaint the line it names immediately; waiting for the next
  // recompute would make choosing a colour feel like a read of the archive, which it
  // is not (design.md, "Kolor rozwiązywany przy rysowaniu z bieżących selekcji").
  const instanceColors = useMemo(
    () => new Map(indicatorSelections.map((selection) => [selection.key, selection.color])),
    [indicatorSelections],
  );

  // The same assignment the sync effect makes, from the same input, kept out of the
  // readout below: `shown` moves on every crosshair pixel and neither `drawnInstances`
  // nor `assignLineColors` needs to redo its work that often.
  const readoutAssignment = useMemo(() => {
    const drawn = drawnInstances(indicatorsState.selections, indicatorsState.results, catalogueById);
    const colors = colorsRef.current ?? readChartColors();
    return { drawn, lineColors: assignLineColors(drawn, colors, instanceColors) };
  }, [indicatorsState.selections, indicatorsState.results, catalogueById, instanceColors, colorsRef]);

  // The header badge says *that* indicators are unavailable; it has nowhere to put *why*
  // except a `title` nobody hovers. The reason is the useful part and is often actionable
  // on the spot — "no MINUTE_5 series collected" is a thing the operator can go and fix —
  // so it is raised where it will be read. Keyed per slot, so a chart requerying on every
  // candle close refreshes one toast instead of stacking one per close, and two slots
  // failing for different reasons still say so separately.
  //
  // Two ways this goes wrong and they read differently. The whole read can fail — the
  // archive is unreachable, or refused the request — and then nothing was computed. Or
  // the archive answered and some indicators came back carrying a reason instead of an
  // answer, which is the archive not holding a series they need; the rest drew fine and
  // the toast has to say which ones did not.
  const indicatorError = indicatorsState.status === "error" ? indicatorsState.error : null;
  const failedIndicators = indicatorsState.results.filter((result) => result.error !== null);
  // A string, not the array: the array is rebuilt every render and would refire the
  // effect on every one of them.
  const failureDigest = failedIndicators.map((r) => `${r.id}: ${r.error}`).join("\n");

  useEffect(() => {
    if (indicatorError === null && failureDigest === "") return;
    const failedCount = failureDigest === "" ? 0 : failureDigest.split("\n").length;
    showToast({
      key: `indicators:${symbol}:${resolution}`,
      severity: "error",
      title:
        indicatorError !== null
          ? `${symbol} · indicators unavailable`
          : `${symbol} · ${failedCount} of the chosen indicators unavailable`,
      detail: indicatorError ?? failureDigest,
    });
  }, [indicatorError, failureDigest, symbol, resolution]);
  const clearIndicatorWindow = useCallback(() => {
    heldIndicatorWindowRef.current = null;
    setBarsRange(null);
  }, []);

  return {
    indicatorSelections,
    setIndicatorSelections,
    catalogue,
    catalogueById,
    knownIndicatorSelections,
    unknownIndicatorIds,
    indicatorsState,
    instanceColors,
    readoutAssignment,
    failedIndicators,
    failureDigest,
    syncIndicatorWindowRef,
    clearIndicatorWindow,
  };
}
