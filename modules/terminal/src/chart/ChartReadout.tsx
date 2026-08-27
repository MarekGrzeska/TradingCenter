import type { ReactNode } from "react";
import type { Bar, Resolution } from "../data/types";
import { formatInstant } from "../ui/formatTime";
import { RESOLUTION_LABEL } from "../ui/resolutionLabel";
import { groupReadoutByIndicator, type IndicatorReadoutEntry } from "./indicatorReadout";
import type { useBarFeed } from "./useBarFeed";
import type { useOlderBars } from "./useOlderBars";
import { Button } from "../ui/Button";

/**
 * Everything the chart says in words rather than in candles. Split out of `Chart.tsx` because none of it
 * touches the charting library — plain components over a bar and a list of numbers.
 */

/**
 * What paging back through the archive is doing, said in the header rather than over the candles: a chart
 * dragging in older history is still worth reading, and a failed page must not hide the series that arrived.
 */
export function OlderHistoryState({ older }: { older: ReturnType<typeof useOlderBars> }) {
  if (older.status === "loading") {
    return (
      <span className="rounded border border-border px-1.5 py-0.5 text-[10px] tracking-wide text-ink-muted uppercase">
        loading older…
      </span>
    );
  }

  if (older.status === "exhausted") {
    return (
      <span
        title="The archive has nothing older for this pair and resolution."
        className="rounded border border-border px-1.5 py-0.5 text-[10px] tracking-wide text-ink-muted uppercase"
      >
        start of history
      </span>
    );
  }

  if (older.status === "error") {
    return (
      <span className="flex items-center gap-1">
        <span
          title={older.error ?? undefined}
          className="rounded border border-critical/40 px-1.5 py-0.5 text-[10px] tracking-wide text-critical uppercase"
        >
          older history failed
        </span>
        <Button
          size="2xs"
          onClick={older.retry}
        >
          Retry
        </Button>
      </span>
    );
  }

  return null;
}

export function OhlcReadout({ bar, indicators }: { bar: Bar; indicators: IndicatorReadoutEntry[] }) {
  return (
    // `tabular-nums` throughout: proportional digits made a price ticking 9.50 → 21000.00 slide the swatch
    // sideways on every frame of a pan. `w-fit` so the tinted background hugs the text.
    <span className="flex w-fit flex-col gap-0.5 rounded bg-panel/75 px-1.5 py-1 text-xs text-ink-secondary tabular-nums">
      <span className="flex flex-wrap items-center gap-2">
        <Field label="O" value={bar.open} />
        <Field label="H" value={bar.high} />
        <Field label="L" value={bar.low} />
        <Field label="C" value={bar.close} />
        <time className="text-ink-muted">{formatInstant(bar.time)}</time>
      </span>
      {/* One row per indicator *kind*, under the OHLC row: several SMAs sit beside each
          other on the row their id owns, and a different indicator always gets a row of
          its own rather than every instance stacking one below another. */}
      {groupReadoutByIndicator(indicators).map((group) => (
        <span
          key={group[0].key}
          data-testid="indicator-readout-row"
          className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-ink-muted"
        >
          {group.map((entry) => (
            <span key={entry.key} className="flex items-center gap-1">
              <span
                aria-hidden
                style={{ backgroundColor: entry.color }}
                className="inline-block h-2 w-2 rounded-sm"
              />
              {entry.label}{" "}
              <span className="text-ink">{entry.value === null ? "…" : entry.value.toFixed(2)}</span>
            </span>
          ))}
        </span>
      ))}
    </span>
  );
}

function Field({ label, value }: { label: string; value: number }) {
  return (
    <span className="text-ink-muted">
      {label} <span className="text-ink">{value}</span>
    </span>
  );
}

export function FeedOverlay({
  feed,
  symbol,
  resolution,
}: {
  feed: ReturnType<typeof useBarFeed>;
  symbol: string;
  resolution: Resolution;
}) {
  if (feed.status === "loading") {
    return (
      <Veil>
        <span className="text-sm text-ink-muted">Loading {symbol} history…</span>
      </Veil>
    );
  }

  if (feed.status === "empty") {
    return (
      <Veil>
        <span className="text-sm text-ink-muted">
          No candles for {symbol} at {RESOLUTION_LABEL[resolution]}.
        </span>
      </Veil>
    );
  }

  if (feed.status === "error") {
    return (
      <Veil>
        <div className="text-center">
          <p className="text-sm text-critical">Could not load {symbol}.</p>
          <p className="mt-1 max-w-xs text-xs text-ink-muted">{feed.error}</p>
          <Button
            className="mt-3"
            onClick={feed.retry}
          >
            Retry
          </Button>
        </div>
      </Veil>
    );
  }

  return null;
}

/**
 * Everything the chart has to say when it cannot draw. `z-10` is load-bearing: the library's canvas container
 * opens no stacking context, so at the default level an empty canvas paints over every message.
 */
function Veil({ children }: { children: ReactNode }) {
  return (
    <div className="absolute inset-0 z-10 flex items-center justify-center bg-panel/80">
      {children}
    </div>
  );
}
