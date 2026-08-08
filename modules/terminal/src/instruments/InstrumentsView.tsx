import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { archive } from "../data/marketData";
import { RESOLUTIONS } from "../data/types";
import type { CollectionState, PairCoverage, Resolution, TrackedPair } from "../data/types";
import { AddInstrumentWizard } from "./AddInstrumentWizard";
import { formatInstant } from "./format";
import { RESOLUTION_ABBR } from "./resolutionAbbr";
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

/** How far back the data reaches, and for which resolutions. One entry when
 *  every resolution reaches equally far back — which is the common case, since
 *  they are usually collected by one job from one date — and one per distinct
 *  moment otherwise. `since` is null for resolutions that have collected
 *  nothing at all. */
interface DataSince {
  since: number | null;
  resolutions: Resolution[];
}

interface InstrumentGroup {
  symbol: string;
  /** Sorted by `RESOLUTIONS`' own order, not insertion order. */
  pairs: TrackedPair[];
  /** Oldest first, so the row leads with the deepest history it has. */
  dataSince: DataSince[];
}

/**
 * Resolutions bucketed by the moment their data starts.
 *
 * An instrument whose four resolutions all begin at the same moment deserves
 * one date, not the same date four times; one whose daily series reaches back
 * years while its minute series reaches back a week deserves both numbers,
 * because a single one of them would be a lie about the other.
 */
function dataSinceOf(pairs: TrackedPair[]): DataSince[] {
  const byMoment = new Map<number | null, Resolution[]>();
  for (const pair of pairs) {
    const at = byMoment.get(pair.earliestCandle) ?? [];
    at.push(pair.resolution);
    byMoment.set(pair.earliestCandle, at);
  }
  return [...byMoment.entries()]
    .map(([since, resolutions]) => ({ since, resolutions }))
    // Nothing collected yet sorts last: it is the least informative line, and
    // an operator scanning the column is looking for how deep the archive goes.
    .sort((a, b) => (a.since ?? Infinity) - (b.since ?? Infinity));
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
      return { symbol, pairs: sorted, dataSince: dataSinceOf(sorted) };
    })
    .sort((a, b) => a.symbol.localeCompare(b.symbol));
}

/** What one Delete left behind — the only thing worth telling the operator
 *  once the row or interval it names is already gone from the list above. */
interface DeletionNotice {
  symbol: string;
  resolutions: Resolution[];
  candlesRemoved: number;
}

/**
 * Deleting cuts the row it names, so the confirmation of what happened can't
 * live there — it lives here instead, above the list, until the operator
 * dismisses it or deletes something else.
 */
function DeletionBanner({ notice, onDismiss }: { notice: DeletionNotice; onDismiss(): void }) {
  return (
    <p className="flex items-center gap-3 border-b border-border bg-panel px-4 py-2 text-xs text-ink-secondary">
      <span>
        Deleted {notice.candlesRemoved.toLocaleString()} candle
        {notice.candlesRemoved === 1 ? "" : "s"} for {notice.symbol} in{" "}
        {notice.resolutions.join(", ")}. See it in the{" "}
        <Link to="/data-history" className="text-ink underline">
          Data History
        </Link>{" "}
        tab.
      </span>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss"
        className="ml-auto text-ink-muted hover:text-ink"
      >
        ×
      </button>
    </p>
  );
}

export function InstrumentsView() {
  const list = useTrackedPairs(archive);
  const groups = useMemo(() => groupBySymbol(list.pairs), [list.pairs]);
  const [deletion, setDeletion] = useState<DeletionNotice | null>(null);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <AddInstrumentWizard existingPairs={list.pairs} onCollected={list.reload} />

      {deletion && <DeletionBanner notice={deletion} onDismiss={() => setDeletion(null)} />}

      <div className="min-h-0 flex-1 overflow-auto">
        <InstrumentList list={list} groups={groups} onDeleted={setDeletion} />
      </div>
    </div>
  );
}

function InstrumentList({
  list,
  groups,
  onDeleted,
}: {
  list: ReturnType<typeof useTrackedPairs>;
  groups: InstrumentGroup[];
  onDeleted(notice: DeletionNotice): void;
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
        <p className="px-4 py-6 text-sm text-ink-muted">
          Nothing is being archived yet. Add an instrument above to start collecting one.
        </p>
      ) : (
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-canvas text-left text-xs text-ink-muted">
            <tr>
              <th className="px-4 py-2 font-normal">Symbol</th>
              <th className="px-4 py-2 font-normal">Resolutions</th>
              <th className="px-4 py-2 font-normal">Data since</th>
              <th className="px-4 py-2 font-normal" />
            </tr>
          </thead>
          <tbody>
            {groups.map((group) => (
              <InstrumentRow
                key={group.symbol}
                group={group}
                onChanged={list.reload}
                onDeleted={onDeleted}
              />
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

function InstrumentRow({
  group,
  onChanged,
  onDeleted,
}: {
  group: InstrumentGroup;
  onChanged(): void;
  onDeleted(notice: DeletionNotice): void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const stalled = group.pairs.some((pair) => pair.collection === "stalled");
  // The deepest history this instrument holds, across every interval — what a
  // confirmation shows so the operator sees the size of what they are about
  // to lose, not just which intervals.
  const earliestData = group.dataSince.find((entry) => entry.since !== null)?.since ?? null;

  const deleteAll = useCallback(async () => {
    setFailure(null);
    const outcomes = await Promise.allSettled(
      group.pairs.map((pair) =>
        archive.deletePair(pair.symbol, pair.resolution, new AbortController().signal),
      ),
    );

    const succeededResolutions: Resolution[] = [];
    const failedResolutions: Resolution[] = [];
    let candlesRemoved = 0;
    outcomes.forEach((outcome, index) => {
      const pair = group.pairs[index];
      if (outcome.status === "fulfilled") {
        succeededResolutions.push(pair.resolution);
        candlesRemoved += outcome.value.candlesRemoved;
      } else {
        failedResolutions.push(pair.resolution);
      }
    });

    if (succeededResolutions.length > 0) {
      onDeleted({ symbol: group.symbol, resolutions: succeededResolutions, candlesRemoved });
      onChanged();
    }

    if (failedResolutions.length > 0) {
      // What is left in `group.pairs` after `onChanged()` reloads is exactly
      // what failed — the confirmation stays open, naming it, rather than
      // closing over a partial success.
      setFailure(`could not delete ${failedResolutions.join(", ")}`);
    } else {
      setConfirming(false);
    }
  }, [group.pairs, group.symbol, onChanged, onDeleted]);

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
        <td className="px-4 py-1.5 text-ink-muted">
          <DataSinceCell entries={group.dataSince} />
        </td>
        <td className="px-4 py-1.5 text-right">
          <button
            type="button"
            aria-label={`Delete ${group.symbol}`}
            onClick={(e) => {
              e.stopPropagation();
              setConfirming(true);
            }}
            className="rounded border border-border px-2 py-0.5 text-xs text-ink-muted hover:text-ink"
          >
            Delete
          </button>
        </td>
      </tr>

      {confirming && (
        <tr className="border-t border-border bg-panel">
          <td colSpan={4} className="px-4 py-2">
            <div className="flex flex-wrap items-center gap-3 text-sm">
              {/* Deletion is irreversible, and the confirmation says so plainly
                  — this replaces the old "the candles stay" assurance, which
                  would now be a lie. */}
              <span className="text-ink">
                Delete {group.symbol} in {group.pairs.map((p) => p.resolution).join(", ")}? This
                permanently removes every candle already collected
                {earliestData !== null && <> (data since {formatInstant(earliestData)})</>} — this
                cannot be undone.
              </span>
              <button
                type="button"
                onClick={deleteAll}
                className="rounded border border-down px-2 py-0.5 text-xs text-down hover:bg-panel-strong"
              >
                Delete data
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
              <IntervalCoverage
                key={pair.resolution}
                pair={pair}
                onChanged={onChanged}
                onDeleted={onDeleted}
              />
            ))}
          </td>
        </tr>
      )}
    </>
  );
}

/**
 * Since when there is data — one date when that answer is one date.
 *
 * The resolutions are named only when they disagree. Labelling a single moment
 * with all four of an instrument's intervals says nothing the row does not
 * already say, and the column exists to be read at a glance.
 */
function DataSinceCell({ entries }: { entries: DataSince[] }) {
  if (entries.length === 1) {
    const [only] = entries;
    return only.since === null ? (
      <span>nothing yet</span>
    ) : (
      <span className="text-ink-secondary">{formatInstant(only.since)}</span>
    );
  }

  return (
    <div className="flex flex-col gap-0.5">
      {entries.map((entry) => (
        <div key={entry.since ?? "none"} className="flex items-baseline gap-2">
          <span className="shrink-0 text-xs">
            {entry.resolutions.map((resolution) => RESOLUTION_ABBR[resolution]).join(" · ")}
          </span>
          <span className={entry.since === null ? "" : "text-ink-secondary"}>
            {entry.since === null ? "nothing yet" : formatInstant(entry.since)}
          </span>
        </div>
      ))}
    </div>
  );
}

function IntervalCoverage({
  pair,
  onChanged,
  onDeleted,
}: {
  pair: TrackedPair;
  onChanged(): void;
  onDeleted(notice: DeletionNotice): void;
}) {
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

  const deleteInterval = useCallback(async () => {
    setFailure(null);
    try {
      const result = await archive.deletePair(
        pair.symbol,
        pair.resolution,
        new AbortController().signal,
      );
      setConfirming(false);
      onDeleted({
        symbol: pair.symbol,
        resolutions: [pair.resolution],
        candlesRemoved: result.candlesRemoved,
      });
      onChanged();
    } catch (cause: unknown) {
      setFailure(cause instanceof Error ? cause.message : "could not delete this interval's data");
    }
  }, [pair.symbol, pair.resolution, onChanged, onDeleted]);

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
          aria-label={`Delete ${pair.symbol} ${pair.resolution}`}
          onClick={() => setConfirming(true)}
          className="ml-auto rounded border border-border px-2 py-0.5 text-ink-muted hover:text-ink"
        >
          Delete
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
            Delete {pair.symbol} {pair.resolution}? This permanently removes every candle already
            collected
            {pair.earliestCandle !== null && <> (data since {formatInstant(pair.earliestCandle)})</>}{" "}
            — this cannot be undone.
          </span>
          <button
            type="button"
            onClick={deleteInterval}
            className="rounded border border-down px-2 py-0.5 text-down hover:bg-panel-strong"
          >
            Delete data
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
