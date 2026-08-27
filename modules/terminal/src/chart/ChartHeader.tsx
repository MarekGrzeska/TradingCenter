import type { ReactNode } from "react";
import { RESOLUTION_LABEL } from "../ui/resolutionLabel";
import { Button } from "../ui/Button";
import type { Resolution } from "../data/types";
import { canDrawIndicator } from "./chartLines";
import { IndicatorPicker } from "./indicators/IndicatorPicker";
import { DrawingList } from "./DrawingList";
import { OlderHistoryState } from "./ChartReadout";
import type { ChartDrawings } from "./Chart";
import type { ChartIndicators } from "./useChartIndicators";
import type { BarFeed } from "./useBarFeed";
import type { OlderBars } from "./useOlderBars";

export interface ChartHeaderProps {
  symbol: string;
  resolution: Resolution;
  resolutions: readonly Resolution[];
  onResolutionChange: (resolution: Resolution) => void;
  headerLeft?: ReactNode;
  /** Whether there is an archive to ask at all — no source is a chart with no picker,
   *  not a picker with nothing in it. */
  hasIndicatorSource: boolean;
  indicators: ChartIndicators;
  drawings?: ChartDrawings;
  selectedId: number | null;
  onSelectDrawing: (id: number | null) => void;
  feed: BarFeed;
  older: OlderBars;
}

/**
 * The row above the canvas. A component rather than a fragment of `Chart.tsx` because none of it touches the
 * chart instance; it takes `useChartIndicators`' return whole, since nine props would hide where they come from.
 */
export function ChartHeader({
  symbol,
  resolution,
  resolutions,
  onResolutionChange,
  headerLeft,
  hasIndicatorSource,
  indicators,
  drawings,
  selectedId,
  onSelectDrawing,
  feed,
  older,
}: ChartHeaderProps) {
  const {
    indicatorSelections,
    setIndicatorSelections,
    catalogue,
    catalogueById,
    knownIndicatorSelections,
    unknownIndicatorIds,
    indicatorsState,
    failedIndicators,
    failureDigest,
  } = indicators;
  const staleStream = feed.streamState === "reconnecting" || feed.streamState === "closed";
  const unsettledIndicators = indicatorsState.results.filter((r) => !r.settled);

  return (
    <header className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1 border-b border-border px-2 py-1.5">
      {headerLeft ?? <span className="text-sm font-semibold text-ink">{symbol}</span>}

      <select
        aria-label="Resolution"
        value={resolution}
        onChange={(e) => onResolutionChange(e.target.value as Resolution)}
        // `h-6` rather than the vertical padding alone: a native `<select>` carries its own intrinsic
        // sizing on top of padding, which made it taller than a `<button>` given identical classes.
        className="h-6 rounded border border-border bg-sunken px-1.5 text-xs text-ink"
      >
        {resolutions.map((r) => (
          <option key={r} value={r}>
            {RESOLUTION_LABEL[r]}
          </option>
        ))}
      </select>

      {/* Grouped with the instrument and interval rather than pushed right with the status badges: this
          is a control the operator reaches for, and the right side of the header sits above the price
          pane, where the current price and its axis label live. */}
      {hasIndicatorSource && (
        <IndicatorPicker
          entries={catalogue.entries}
          selections={knownIndicatorSelections}
          onChange={(next) => {
            // An unknown selection is never touched by an edit to a known one — only a later catalogue
            // read that recognizes it again moves it out of this list.
            const stillUnknown = indicatorSelections.filter((s) => !catalogueById.has(s.id));
            setIndicatorSelections([...stillUnknown, ...next]);
          }}
          canDraw={canDrawIndicator}
        />
      )}

      {/* Beside the indicator picker, and for the same reason it is there rather than
          in the agent panel: this is the one place the operator undoes what the agent
          drew, and it has to be reachable without a conversation (`agent-tools` spec,
          "Zapis MUST być odwracalny ręką operatora"). */}
      {drawings && (
        <DrawingList
          drawings={drawings}
          selectedId={selectedId}
          // Picked from the list, so there is no click on the chart to sit beside — the
          // card takes its own corner (`DrawingCard.cardPosition`).
          onSelect={onSelectDrawing}
        />
      )}

      <div className="ml-auto flex items-center gap-2">
        {unknownIndicatorIds.length > 0 && (
          <span
            title={`No longer offered by the indicator catalogue: ${unknownIndicatorIds.join(", ")}`}
            className="rounded border border-warning/40 px-1.5 py-0.5 text-[10px] tracking-wide text-warning uppercase"
          >
            {unknownIndicatorIds.length} saved {unknownIndicatorIds.length === 1 ? "indicator" : "indicators"}{" "}
            unavailable
          </span>
        )}
        {unsettledIndicators.length > 0 && (
          <span
            title="The archive did not hold enough history before this range for every value to be trusted yet."
            className="rounded border border-warning/40 px-1.5 py-0.5 text-[10px] tracking-wide text-warning uppercase"
          >
            warming up
          </span>
        )}
        {failedIndicators.length > 0 && (
          // Named by id rather than counted: with several chosen, "one is unavailable" sends the operator
          // looking for which.
          <span
            title={failureDigest}
            className="rounded border border-critical/40 px-1.5 py-0.5 text-[10px] tracking-wide text-critical uppercase"
          >
            {failedIndicators.map((result) => result.id).join(", ")} unavailable
          </span>
        )}
        {indicatorsState.status === "error" && (
          <span className="flex items-center gap-1">
            <span
              title={indicatorsState.error ?? undefined}
              className="rounded border border-critical/40 px-1.5 py-0.5 text-[10px] tracking-wide text-critical uppercase"
            >
              indicators unavailable
            </span>
            <Button
              size="2xs"
              onClick={indicatorsState.retry}
            >
              Retry
            </Button>
          </span>
        )}
        <OlderHistoryState older={older} />
        {staleStream && (
          <span className="rounded border border-down/40 px-1.5 py-0.5 text-[10px] tracking-wide text-down uppercase">
            {feed.streamState === "closed" ? "stream closed" : "reconnecting"}
          </span>
        )}
      </div>
    </header>
  );
}
