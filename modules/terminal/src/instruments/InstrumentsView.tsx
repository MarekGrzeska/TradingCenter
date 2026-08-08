import { useCallback, useEffect, useMemo, useState } from "react";
import { archive } from "../data/marketData";
import { RESOLUTIONS } from "../data/types";
import type { CollectionState, PairCoverage, Resolution, TrackedPair } from "../data/types";
import { useTrackedPairs } from "./useTrackedPairs";

/**
 * What the archive is collecting, one row per instrument.
 *
 * This used to be two tabs: a catalogue browser and a per-pair archive list,
 * where the same instrument in four resolutions took four rows. Neither
 * question the operator actually asks — *what are we archiving, and is it
 * keeping up* — was answered by either one directly (proposal.md, Why). This
 * view answers both: a row is an instrument, its resolutions are one column,
 * and expanding it shows coverage and lets a resolution — or the whole
 * instrument — stop being collected.
 */

function formatInstant(epochSeconds: number): string {
  return `${new Date(epochSeconds * 1000).toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

const COLLECTION_LABEL: Record<CollectionState, string> = {
  never_collected: "nothing yet",
  collecting: "collecting",
  stalled: "stalled",
  market_closed: "market closed",
  unknown: "unknown",
};

const COLLECTION_HINT: Record<CollectionState, string> = {
  never_collected: "Added, but no candle has been written yet.",
  collecting: "The newest candle is as recent as it should be.",
  stalled: "The newest candle is older than two periods and the market is open — nothing is arriving.",
  market_closed: "Behind, but the market is shut, so there is nothing to collect.",
  unknown: "Behind, and nobody could say whether the market is open.",
};

const RESOLUTION_ABBR: Record<Resolution, string> = {
  MINUTE: "1m",
  MINUTE_5: "5m",
  MINUTE_15: "15m",
  MINUTE_30: "30m",
  HOUR: "1h",
  HOUR_4: "4h",
  DAY: "1D",
  WEEK: "1W",
};

interface InstrumentGroup {
  symbol: string;
  /** Sorted by `RESOLUTIONS`' own order, not insertion order. */
  pairs: TrackedPair[];
  /** The earliest of its resolutions' `addedAt` — when archiving this
   *  instrument began, not any one resolution added to it later. */
  archivingSince: number;
}

function groupBySymbol(pairs: TrackedPair[]): InstrumentGroup[] {
  const bySymbol = new Map<string, TrackedPair[]>();
  for (const pair of pairs) {
    const group = bySymbol.get(pair.symbol) ?? [];
    group.push(pair);
    bySymbol.set(pair.symbol, group);
  }
  return [...bySymbol.entries()]
    .map(([symbol, group]) => {
      const sorted = [...group].sort(
        (a, b) => RESOLUTIONS.indexOf(a.resolution) - RESOLUTIONS.indexOf(b.resolution),
      );
      return {
        symbol,
        pairs: sorted,
        archivingSince: Math.min(...sorted.map((pair) => pair.addedAt)),
      };
    })
    .sort((a, b) => a.symbol.localeCompare(b.symbol));
}

export function InstrumentsView() {
  const list = useTrackedPairs(archive);
  const groups = useMemo(() => groupBySymbol(list.pairs), [list.pairs]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 overflow-auto">
        <InstrumentList list={list} groups={groups} />
      </div>
    </div>
  );
}

function InstrumentList({
  list,
  groups,
}: {
  list: ReturnType<typeof useTrackedPairs>;
  groups: InstrumentGroup[];
}) {
  if (list.status === "loading") {
    return <p className="px-4 py-6 text-sm text-ink-muted">Reading the archive…</p>;
  }

  // An empty list and an unanswered question are the same empty array, and
  // only one of them means the operator has nothing set up.
  if (list.status === "unreachable") {
    return (
      <p className="px-4 py-6 text-sm text-critical">
        The archive is not reachable, so what it is collecting is unknown — this is not an
        empty list. {list.error}
        <button
          type="button"
          onClick={list.reload}
          className="ml-3 rounded border border-border px-2 py-0.5 text-xs text-ink hover:bg-panel-strong"
        >
          Retry
        </button>
      </p>
    );
  }

  return (
    <>
      {list.error && (
        // The rows below are the last good answer; saying so beats replacing
        // them with an error over one missed refresh.
        <p className="px-4 pt-3 text-xs text-warning">
          The last refresh failed ({list.error}); the rows below may be out of date.
        </p>
      )}

      {groups.length === 0 ? (
        <p className="px-4 py-6 text-sm text-ink-muted">Nothing is being archived yet.</p>
      ) : (
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-canvas text-left text-xs text-ink-muted">
            <tr>
              <th className="px-4 py-2 font-normal">Symbol</th>
              <th className="px-4 py-2 font-normal">Resolutions</th>
              <th className="px-4 py-2 font-normal">Archiving since</th>
              <th className="px-4 py-2 font-normal" />
            </tr>
          </thead>
          <tbody>
            {groups.map((group) => (
              <InstrumentRow key={group.symbol} group={group} onChanged={list.reload} />
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

function InstrumentRow({ group, onChanged }: { group: InstrumentGroup; onChanged(): void }) {
  const [expanded, setExpanded] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const stalled = group.pairs.some((pair) => pair.collection === "stalled");

  const removeAll = useCallback(async () => {
    setFailure(null);
    try {
      await Promise.all(
        group.pairs.map((pair) =>
          archive.untrackPair(pair.symbol, pair.resolution, new AbortController().signal),
        ),
      );
      setConfirming(false);
      onChanged();
    } catch (cause: unknown) {
      setFailure(cause instanceof Error ? cause.message : "could not stop collecting");
    }
  }, [group.pairs, onChanged]);

  return (
    <>
      <tr
        onClick={() => setExpanded((v) => !v)}
        data-testid={`instrument-${group.symbol}`}
        data-stalled={stalled}
        className={`cursor-pointer border-t border-border hover:bg-panel ${
          stalled ? "border-l-2 border-l-down" : ""
        }`}
      >
        <td className="px-4 py-1.5 font-semibold text-ink">{group.symbol}</td>
        <td className="px-4 py-1.5">
          {group.pairs.map((pair, index) => (
            <span key={pair.resolution}>
              {index > 0 && <span className="text-ink-muted"> · </span>}
              <span
                title={COLLECTION_HINT[pair.collection]}
                className={
                  pair.collection === "stalled" ? "font-semibold text-down" : "text-ink-secondary"
                }
              >
                {RESOLUTION_ABBR[pair.resolution]}
              </span>
            </span>
          ))}
        </td>
        <td className="px-4 py-1.5 text-ink-muted">{formatInstant(group.archivingSince)}</td>
        <td className="px-4 py-1.5 text-right">
          <button
            type="button"
            aria-label={`Stop archiving ${group.symbol}`}
            onClick={(e) => {
              e.stopPropagation();
              setConfirming(true);
            }}
            className="rounded border border-border px-2 py-0.5 text-xs text-ink-muted hover:text-ink"
          >
            Stop
          </button>
        </td>
      </tr>

      {confirming && (
        <tr className="border-t border-border bg-panel">
          <td colSpan={4} className="px-4 py-2">
            <div className="flex flex-wrap items-center gap-3 text-sm">
              {/* Stopping is deliberate, and worth saying plainly that it costs
                  nothing already collected — an archive that dropped data when
                  its configuration changed would not be an archive. */}
              <span className="text-ink">
                Stop archiving {group.symbol} in {group.pairs.map((p) => p.resolution).join(", ")}?
                The candles already collected stay in the archive.
              </span>
              <button
                type="button"
                onClick={removeAll}
                className="rounded border border-down px-2 py-0.5 text-xs text-down hover:bg-panel-strong"
              >
                Stop collecting
              </button>
              <button
                type="button"
                onClick={() => setConfirming(false)}
                className="rounded border border-border px-2 py-0.5 text-xs text-ink-muted hover:text-ink"
              >
                Cancel
              </button>
              {failure && <span className="text-critical">{failure}</span>}
            </div>
          </td>
        </tr>
      )}

      {expanded && (
        <tr className="border-t border-border">
          <td colSpan={4} className="p-0">
            {group.pairs.map((pair) => (
              <IntervalCoverage key={pair.resolution} pair={pair} onChanged={onChanged} />
            ))}
          </td>
        </tr>
      )}
    </>
  );
}

function IntervalCoverage({ pair, onChanged }: { pair: TrackedPair; onChanged(): void }) {
  const [coverage, setCoverage] = useState<PairCoverage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    setCoverage(null);
    setError(null);

    archive
      .coverage(pair.symbol, pair.resolution, controller.signal)
      .then((result) => {
        if (!cancelled) setCoverage(result);
      })
      .catch((cause: unknown) => {
        if (cancelled || controller.signal.aborted) return;
        setError(cause instanceof Error ? cause.message : "could not read coverage");
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [pair.symbol, pair.resolution]);

  const remove = useCallback(async () => {
    setFailure(null);
    try {
      await archive.untrackPair(pair.symbol, pair.resolution, new AbortController().signal);
      setConfirming(false);
      onChanged();
    } catch (cause: unknown) {
      setFailure(cause instanceof Error ? cause.message : "could not stop collecting");
    }
  }, [pair.symbol, pair.resolution, onChanged]);

  const first = coverage?.ranges[0];
  const last = coverage?.ranges.at(-1);
  const stalled = pair.collection === "stalled";

  return (
    <div className="flex flex-col gap-1 border-t border-border px-4 py-2 text-xs first:border-t-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold text-ink">{RESOLUTION_ABBR[pair.resolution]}</span>
        <span
          title={COLLECTION_HINT[pair.collection]}
          className={stalled ? "font-semibold text-down" : "text-ink-secondary"}
        >
          {COLLECTION_LABEL[pair.collection]}
        </span>
        <span className="text-ink-muted">
          newest: {pair.latestCandle === null ? "—" : formatInstant(pair.latestCandle)}
        </span>
        <button
          type="button"
          aria-label={`Stop archiving ${pair.symbol} ${pair.resolution}`}
          onClick={() => setConfirming(true)}
          className="ml-auto rounded border border-border px-2 py-0.5 text-ink-muted hover:text-ink"
        >
          Stop
        </button>
      </div>

      {error && <p className="text-critical">{error}</p>}
      {!error && !coverage && <p className="text-ink-muted">Reading coverage…</p>}
      {coverage &&
        (first && last ? (
          <p className="text-ink-secondary">
            Covered from <span className="text-ink">{formatInstant(first.from)}</span> to{" "}
            <span className="text-ink">{formatInstant(last.to)}</span>
            {coverage.ranges.length > 1 && (
              // Coverage is stored merged, so more than one range means real
              // stretches nobody has looked at between them.
              <span className="text-warning">
                {" "}
                — in {coverage.ranges.length} stretches, with gaps between them
              </span>
            )}{" "}
            {first.historyEnded
              ? "— reached the end of the provider's history."
              : coverage.earliestReachable === null
                ? "— the provider's history has not been reached yet."
                : `— the provider has nothing older than ${formatInstant(coverage.earliestReachable)}.`}
          </p>
        ) : (
          <p className="text-ink-muted">Nothing verified yet for this interval.</p>
        ))}

      {confirming && (
        <div className="flex flex-wrap items-center gap-3 rounded border border-border bg-panel px-2 py-1.5">
          <span className="text-ink">
            Stop archiving {pair.symbol} {pair.resolution}? The candles already collected stay in
            the archive.
          </span>
          <button
            type="button"
            onClick={remove}
            className="rounded border border-down px-2 py-0.5 text-down hover:bg-panel-strong"
          >
            Stop collecting
          </button>
          <button
            type="button"
            onClick={() => setConfirming(false)}
            className="rounded border border-border px-2 py-0.5 text-ink-muted hover:text-ink"
          >
            Cancel
          </button>
          {failure && <span className="text-critical">{failure}</span>}
        </div>
      )}
    </div>
  );
}
