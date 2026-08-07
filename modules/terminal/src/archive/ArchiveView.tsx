import { useCallback, useEffect, useState } from "react";
import { archive, marketData } from "../data/marketData";
import { useInstrumentSearch } from "../instruments/useInstrumentSearch";
import { RESOLUTIONS, type CollectionState, type PairCoverage, type Resolution, type TrackedPair } from "../data/types";
import { useTrackedPairs } from "./useTrackedPairs";

/**
 * Where the operator decides what the archive collects.
 *
 * Collecting a pair holds a provider connection open around the clock and the
 * provider limits how many a session may hold, so the list is a standing
 * decision rather than a side effect of looking at a chart — and this is where
 * that decision is made and taken back (design.md, "Śledzone pary są jawną
 * decyzją operatora, podejmowaną w terminalu").
 *
 * The panel's other job is doubt: a pair on the list proves nothing about data
 * arriving. Every row carries how collection is going and how fresh the newest
 * candle is, so a subscription that died quietly is visible here instead of in
 * a log.
 */

function pairKey(pair: { symbol: string; resolution: Resolution }): string {
  return `${pair.symbol}|${pair.resolution}`;
}

/** UTC to the minute — the archive keys candles on an instant, and a local
 *  rendering of one invites comparing it against a period start that is not in
 *  the same zone. */
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

export function ArchiveView() {
  const list = useTrackedPairs(archive);
  const [selected, setSelected] = useState<string | null>(null);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <AddPairForm existing={list.pairs} onAdded={list.reload} />

      <div className="min-h-0 flex-1 overflow-auto">
        <PairList list={list} selected={selected} onSelect={setSelected} />
      </div>

      {selected && <CoveragePanel pairKey={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

// --- adding ---

function AddPairForm({
  existing,
  onAdded,
}: {
  existing: TrackedPair[];
  onAdded(): void;
}) {
  const [query, setQuery] = useState("");
  const [symbol, setSymbol] = useState<string | null>(null);
  const [resolution, setResolution] = useState<Resolution>("MINUTE");
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [added, setAdded] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // The instruments come from the search rather than a text field, so the
  // operator never types a symbol from memory into a decision that holds a
  // connection open (terminal-data-manager spec, "Operator dokłada parę").
  const search = useInstrumentSearch(marketData, symbol === null ? query : "");

  const submit = useCallback(async () => {
    if (!symbol) return;
    setRefusal(null);
    setAdded(null);
    setNotice(null);

    // Already on the list: said here rather than sent. The archive would take
    // the request and overwrite the row without duplicating it, but an operator
    // asking twice is asking a question, and "it is already being collected" is
    // the answer to it.
    if (existing.some((pair) => pair.symbol === symbol && pair.resolution === resolution)) {
      setNotice(`${symbol} ${resolution} is already being archived.`);
      return;
    }

    setBusy(true);
    try {
      const pair = await archive.trackPair(symbol, resolution, new AbortController().signal);
      setAdded(`${pair.symbol} ${pair.resolution}`);
      setSymbol(null);
      setQuery("");
      onAdded();
    } catch (cause: unknown) {
      // The reason, verbatim: a ceiling reached names the count and the setting
      // to raise, and an operator can act on that. Replacing it with "could not
      // add" would throw away the only useful part.
      setRefusal(cause instanceof Error ? cause.message : "the archive refused to add this pair");
    } finally {
      setBusy(false);
    }
  }, [symbol, resolution, existing, onAdded]);

  return (
    <div className="shrink-0 border-b border-border px-4 py-3">
      <div className="flex flex-wrap items-center gap-3">
        {symbol === null ? (
          <input
            aria-label="Find an instrument to archive"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Find an instrument…"
            spellCheck={false}
            autoComplete="off"
            className="w-72 rounded border border-border bg-panel px-2 py-1 text-sm text-ink placeholder:text-ink-muted"
          />
        ) : (
          <span className="flex items-center gap-2 rounded border border-accent px-2 py-1 text-sm text-ink">
            {symbol}
            <button
              type="button"
              aria-label="Choose a different instrument"
              onClick={() => setSymbol(null)}
              className="text-xs text-ink-muted hover:text-ink"
            >
              ×
            </button>
          </span>
        )}

        <label className="flex items-center gap-2 text-xs text-ink-muted">
          Resolution
          <select
            aria-label="Resolution to archive"
            value={resolution}
            onChange={(e) => setResolution(e.target.value as Resolution)}
            className="rounded border border-border bg-panel-strong px-1.5 py-1 text-xs text-ink"
          >
            {RESOLUTIONS.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>

        <button
          type="button"
          disabled={symbol === null || busy}
          onClick={submit}
          className="rounded border border-border px-2 py-1 text-xs text-ink hover:bg-panel-strong disabled:opacity-40"
        >
          {busy ? "Starting…" : "Start collecting"}
        </button>

        {added && <span className="text-xs text-up">Collecting {added}.</span>}
        {notice && <span className="text-xs text-warning">{notice}</span>}
      </div>

      {refusal && (
        <p role="alert" className="mt-2 text-sm text-critical">
          The archive refused: {refusal}
        </p>
      )}

      {symbol === null && query.trim() !== "" && (
        <SearchResults search={search} onPick={setSymbol} query={query} />
      )}
    </div>
  );
}

function SearchResults({
  search,
  onPick,
  query,
}: {
  search: ReturnType<typeof useInstrumentSearch>;
  onPick(symbol: string): void;
  query: string;
}) {
  if (search.status === "searching") {
    return <p className="mt-2 text-xs text-ink-muted">Searching…</p>;
  }
  if (search.status === "error") {
    return (
      <p className="mt-2 text-xs text-critical">
        Instrument search failed: {search.error}
      </p>
    );
  }
  if (search.status === "no-results") {
    return <p className="mt-2 text-xs text-ink-muted">Nothing matches “{query.trim()}”.</p>;
  }
  return (
    <ul className="mt-2 max-h-40 overflow-auto rounded border border-border">
      {search.instruments.map((instrument) => (
        <li key={instrument.symbol}>
          <button
            type="button"
            onClick={() => onPick(instrument.symbol)}
            className="flex w-full items-center gap-3 px-2 py-1 text-left text-xs hover:bg-panel"
          >
            <span className="font-semibold text-ink">{instrument.symbol}</span>
            <span className="text-ink-secondary">{instrument.name}</span>
            <span className="ml-auto text-ink-muted">{instrument.assetClass}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

// --- the list ---

function PairList({
  list,
  selected,
  onSelect,
}: {
  list: ReturnType<typeof useTrackedPairs>;
  selected: string | null;
  onSelect(key: string | null): void;
}) {
  if (list.status === "loading") {
    return <p className="px-4 py-6 text-sm text-ink-muted">Reading the archive…</p>;
  }

  // An empty list and an unanswered question are the same empty array, and only
  // one of them means the operator has nothing set up.
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

      {list.pairs.length === 0 ? (
        <p className="px-4 py-6 text-sm text-ink-muted">
          Nothing is being archived yet. Pick an instrument above to start collecting one.
        </p>
      ) : (
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-canvas text-left text-xs text-ink-muted">
            <tr>
              <th className="px-4 py-2 font-normal">Symbol</th>
              <th className="px-4 py-2 font-normal">Resolution</th>
              <th className="px-4 py-2 font-normal">Collection</th>
              <th className="px-4 py-2 font-normal">Newest candle</th>
              <th className="px-4 py-2 font-normal">Archiving since</th>
              <th className="px-4 py-2 font-normal" />
            </tr>
          </thead>
          <tbody>
            {list.pairs.map((pair) => (
              <PairRow
                key={pairKey(pair)}
                pair={pair}
                selected={selected === pairKey(pair)}
                onSelect={() => onSelect(selected === pairKey(pair) ? null : pairKey(pair))}
                onChanged={list.reload}
              />
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

function PairRow({
  pair,
  selected,
  onSelect,
  onChanged,
}: {
  pair: TrackedPair;
  selected: boolean;
  onSelect(): void;
  onChanged(): void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const stalled = pair.collection === "stalled";

  const stop = useCallback(async () => {
    setFailure(null);
    try {
      await archive.untrackPair(pair.symbol, pair.resolution, new AbortController().signal);
      setConfirming(false);
      onChanged();
    } catch (cause: unknown) {
      setFailure(cause instanceof Error ? cause.message : "could not stop collecting");
    }
  }, [pair.symbol, pair.resolution, onChanged]);

  return (
    <>
      <tr
        onClick={onSelect}
        data-testid={`pair-${pairKey(pair)}`}
        data-stalled={stalled}
        className={`cursor-pointer border-t border-border hover:bg-panel ${
          selected ? "bg-panel" : ""
        } ${stalled ? "border-l-2 border-l-down" : ""}`}
      >
        <td className="px-4 py-1.5 font-semibold text-ink">{pair.symbol}</td>
        <td className="px-4 py-1.5 text-ink-secondary">{pair.resolution}</td>
        <td className="px-4 py-1.5">
          <span
            title={COLLECTION_HINT[pair.collection]}
            className={stalled ? "font-semibold text-down" : "text-ink-secondary"}
          >
            {COLLECTION_LABEL[pair.collection]}
          </span>
        </td>
        <td className="px-4 py-1.5 text-ink-secondary">
          {pair.latestCandle === null ? (
            <span className="text-ink-muted">—</span>
          ) : (
            formatInstant(pair.latestCandle)
          )}
        </td>
        <td className="px-4 py-1.5 text-ink-muted">{formatInstant(pair.addedAt)}</td>
        <td className="px-4 py-1.5 text-right">
          <button
            type="button"
            aria-label={`Stop archiving ${pair.symbol} ${pair.resolution}`}
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
          <td colSpan={6} className="px-4 py-2">
            <div className="flex flex-wrap items-center gap-3 text-sm">
              {/* Stopping is deliberate, and worth saying plainly that it costs
                  nothing already collected — an archive that dropped data when
                  its configuration changed would not be an archive. */}
              <span className="text-ink">
                Stop archiving {pair.symbol} {pair.resolution}? The candles already collected
                stay in the archive.
              </span>
              <button
                type="button"
                onClick={stop}
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
    </>
  );
}

// --- coverage ---

function CoveragePanel({ pairKey: key, onClose }: { pairKey: string; onClose(): void }) {
  const [symbol, resolution] = key.split("|") as [string, Resolution];
  const [coverage, setCoverage] = useState<PairCoverage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    setCoverage(null);
    setError(null);

    archive
      .coverage(symbol, resolution, controller.signal)
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
  }, [symbol, resolution]);

  const first = coverage?.ranges[0];
  const last = coverage?.ranges.at(-1);

  return (
    <aside className="shrink-0 border-t border-border bg-panel px-4 py-3 text-sm">
      <div className="flex items-center gap-3">
        <span className="font-semibold text-ink">
          Coverage · {symbol} {resolution}
        </span>
        <button
          type="button"
          aria-label="Close coverage"
          onClick={onClose}
          className="ml-auto text-xs text-ink-muted hover:text-ink"
        >
          ×
        </button>
      </div>

      {error && <p className="mt-2 text-critical">{error}</p>}

      {!error && !coverage && <p className="mt-2 text-ink-muted">Reading coverage…</p>}

      {coverage &&
        (first && last ? (
          <div className="mt-2 space-y-1 text-ink-secondary">
            <p>
              Covered from <span className="text-ink">{formatInstant(first.from)}</span> to{" "}
              <span className="text-ink">{formatInstant(last.to)}</span>
              {coverage.ranges.length > 1 && (
                // Coverage is stored merged, so more than one range means real
                // stretches nobody has looked at between them.
                <span className="text-warning">
                  {" "}
                  — in {coverage.ranges.length} stretches, with gaps between them
                </span>
              )}
            </p>
            <p className="text-xs text-ink-muted">
              {first.historyEnded
                ? "The oldest edge is the end of the provider's history — there is nothing older to fetch."
                : coverage.earliestReachable === null
                  ? "The provider's history has not been reached yet, so the oldest edge is just where backfill has got to."
                  : `The provider has nothing older than ${formatInstant(coverage.earliestReachable)}.`}
            </p>
          </div>
        ) : (
          <p className="mt-2 text-ink-muted">
            Nothing verified yet — the archive has not confirmed any stretch of time for this
            pair.
          </p>
        ))}
    </aside>
  );
}
