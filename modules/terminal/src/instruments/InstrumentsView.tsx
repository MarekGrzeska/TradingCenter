import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { archive } from "../data/marketData";
import { RESOLUTIONS } from "../data/types";
import type { CollectionState, PairCoverage, Resolution, TrackedPair } from "../data/types";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { AddInstrumentWizard } from "./AddInstrumentWizard";
import { formatBytes, formatInstant } from "../ui/formatTime";
import { RESOLUTION_LABEL } from "../ui/resolutionLabel";
import { useTrackedPairs } from "./useTrackedPairs";

/**
 * What the archive is collecting, one row per instrument — because the questions an
 * operator actually asks are *what are we archiving* and *is it keeping up*, and the two
 * tabs this replaced answered neither directly (proposal.md, Why). Resolutions are a
 * column, and expanding a row shows coverage and stops collection.
 */

const COLLECTION_HINT: Record<CollectionState, string> = {
  never_collected: "Added, but no candle has been written yet.",
  collecting: "The newest candle is as recent as it should be.",
  stalled: "The newest candle is older than two periods and the market is open — nothing is arriving.",
  market_closed: "Behind, but the market is shut, so there is nothing to collect.",
  unknown: "Behind, and nobody could say whether the market is open.",
};

interface InstrumentGroup {
  symbol: string;
  /** Sorted by `RESOLUTIONS`' own order, not insertion order. */
  pairs: TrackedPair[];
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
      return { symbol, pairs: sorted };
    })
    .sort((a, b) => a.symbol.localeCompare(b.symbol));
}

/** The deepest history this instrument holds, across every interval — what a
 *  whole-instrument delete confirmation shows so the operator sees the size
 *  of what they are about to lose. Null when no interval has collected
 *  anything yet. */
function earliestDataOf(pairs: TrackedPair[]): number | null {
  return pairs.reduce<number | null>((oldest, pair) => {
    if (pair.earliestCandle === null) return oldest;
    if (oldest === null) return pair.earliestCandle;
    return Math.min(oldest, pair.earliestCandle);
  }, null);
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

/**
 * The one confirmation both Delete buttons raise, on the terminal's shared dialog
 * — deleting is the same weight of decision as starting to collect, and the two
 * must not read differently (`terminal-dialogs` spec).
 *
 * It owns nothing but what the question says. `onConfirm` does the deleting and
 * *throws* what failed: staying open, naming the reason and offering another go
 * belong to the dialog, so neither call site writes that again.
 */
function DeleteDialog({
  symbol,
  resolutions,
  dataSince,
  onConfirm,
  onCancel,
}: {
  symbol: string;
  resolutions: Resolution[];
  dataSince: number | null;
  onConfirm(): void | Promise<void>;
  onCancel(): void;
}) {
  return (
    <ConfirmDialog
      title={`Delete ${symbol}?`}
      confirmLabel="Delete data"
      busyLabel="Deleting…"
      tone="danger"
      fallbackError="could not delete this data"
      onConfirm={onConfirm}
      onClose={onCancel}
    >
      <p className="mt-3 text-ink">
        This permanently removes every candle collected for{" "}
        <span className="text-ink">{resolutions.join(", ")}</span>, and the record of what was
        covered. It cannot be undone.
      </p>

      {dataSince !== null && (
        <p className="mt-2 text-ink-secondary">
          Data reaches back to <span className="text-ink">{formatInstant(dataSince)}</span>.
        </p>
      )}

      <p className="mt-2 text-ink-muted">
        Collecting stops too — add the instrument again to start over from a new date.
      </p>
    </ConfirmDialog>
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
          <thead className="sticky top-0 border-b border-secondary-line bg-canvas text-left text-[11px] uppercase tracking-wide text-secondary">
            <tr>
              <th className="px-4 py-2 font-normal">Symbol</th>
              <th className="px-4 py-2 font-normal">Resolutions</th>
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
  const stalled = group.pairs.some((pair) => pair.collection === "stalled");
  const earliestData = earliestDataOf(group.pairs);

  const deleteAll = useCallback(async () => {
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
      // what failed. Thrown rather than returned: the dialog stays open on a
      // rejection and names it, which is what a partial success has to look
      // like — never a dialog that closes over half a job.
      throw new Error(`could not delete ${failedResolutions.join(", ")}`);
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
                  pair.collection === "stalled" ? "font-semibold text-critical" : "text-ink-secondary"
                }
              >
                {RESOLUTION_LABEL[pair.resolution]}
              </span>
            </span>
          ))}
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
        <tr>
          <td colSpan={3} className="p-0">
            <DeleteDialog
              symbol={group.symbol}
              resolutions={group.pairs.map((pair) => pair.resolution)}
              dataSince={earliestData}
              onConfirm={deleteAll}
              onCancel={() => setConfirming(false)}
            />
          </td>
        </tr>
      )}

      {expanded && (
        <tr className="border-t border-border">
          <td colSpan={3} className="p-0">
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
 * How much of this interval is actually archived: how many candles, roughly how much
 * storage they take, and since when — the question expanding a row exists to answer
 * (`terminal-data-manager` spec, "Rozwinięcie instrumentu podaje objętość zebranych
 * danych"). An interval that has collected nothing says so, rather than showing a zero
 * that could be mistaken for a measurement.
 */
function IntervalVolume({ pair }: { pair: TrackedPair }) {
  if (pair.candleCount === 0) {
    // Spans the three number columns: there is no number to line up with.
    return <span className="col-span-3 text-ink-muted">nothing collected yet</span>;
  }
  return (
    <>
      {/* Right-aligned so the counts stack by their ones place down the column, and
          `tabular-nums` so the digits are the same width — without it a column of
          proportional figures still zig-zags. */}
      <span className="text-right tabular-nums text-ink-secondary">
        {pair.candleCount.toLocaleString()} candles
      </span>
      <span className="text-right tabular-nums text-ink-secondary">
        {formatBytes(pair.estimatedBytes)}
      </span>
      <span className="text-ink-secondary">
        {pair.earliestCandle !== null && (
          <>
            since <span className="text-ink">{formatInstant(pair.earliestCandle)}</span>
          </>
        )}
      </span>
    </>
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
    // A rejection here is the dialog's to show — it stays open, names the
    // reason and leaves another go on the table.
    const result = await archive.deletePair(
      pair.symbol,
      pair.resolution,
      new AbortController().signal,
    );
    onDeleted({
      symbol: pair.symbol,
      resolutions: [pair.resolution],
      candlesRemoved: result.candlesRemoved,
    });
    onChanged();
  }, [pair.symbol, pair.resolution, onChanged, onDeleted]);

  return (
    <div className="flex flex-col gap-1 border-t border-border px-4 py-2 text-xs first:border-t-0">
      {/* One grid template, identical in every interval row, so the columns line up
          down the whole expansion — which is the point: an operator compares m1's
          count against h4's by reading down, not by re-reading each line. */}
      <div className="grid grid-cols-[2.5rem_7rem_4.5rem_1fr_auto] items-center gap-x-4">
        <span className="font-semibold text-ink">{RESOLUTION_LABEL[pair.resolution]}</span>
        <IntervalVolume pair={pair} />
        <button
          type="button"
          aria-label={`Delete ${pair.symbol} ${pair.resolution}`}
          onClick={() => setConfirming(true)}
          className="rounded border border-border px-2 py-0.5 text-ink-muted hover:text-ink"
        >
          Delete
        </button>
      </div>

      {error && <p className="text-critical">{error}</p>}
      {/* Silent unless there is something to warn about: a fully covered interval's
          bounds are already said by "since", above — repeating them here would say
          nothing the operator does not already know. */}
      {!error && coverage && coverage.ranges.length > 1 && (
        <p className="text-warning">
          Coverage has gaps — {coverage.ranges.length} stretches, not one continuous range.
        </p>
      )}

      {confirming && (
        <DeleteDialog
          symbol={pair.symbol}
          resolutions={[pair.resolution]}
          dataSince={pair.earliestCandle}
          onConfirm={deleteInterval}
          onCancel={() => setConfirming(false)}
        />
      )}
    </div>
  );
}
