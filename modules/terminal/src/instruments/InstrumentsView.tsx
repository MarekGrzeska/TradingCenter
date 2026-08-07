import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import { useNavigate } from "react-router";
import { marketData } from "../data/marketData";
import { gridStore } from "../grid/gridStore";
import type { Instrument, InstrumentPage } from "../data/types";
import { useInstrumentSearch } from "./useInstrumentSearch";

export function InstrumentsView() {
  const config = useSyncExternalStore(gridStore.subscribe, gridStore.getSnapshot);
  const navigate = useNavigate();

  const [query, setQuery] = useState("");
  const search = useInstrumentSearch(marketData, query);

  const assign = useCallback(
    (instrument: Instrument) => {
      // Straight into the active slot and onto the chart — no manual tab
      // switch (terminal-instruments spec, "Wstawienie instrumentu do slotu").
      gridStore.assignToActiveSlot(instrument.symbol);
      navigate("/graph");
    },
    [navigate],
  );

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-border px-4 py-3">
        <input
          aria-label="Search instruments"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search instruments…"
          spellCheck={false}
          autoComplete="off"
          className="w-72 rounded border border-border bg-panel px-2 py-1 text-sm text-ink placeholder:text-ink-muted"
        />
        <span className="text-xs text-ink-muted">
          Selecting an instrument fills slot <strong className="text-ink">{config.activeSlot}</strong>
        </span>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        {query.trim() === "" ? (
          <Catalogue onPick={assign} />
        ) : (
          <SearchResults search={search} onPick={assign} query={query} />
        )}
      </div>
    </div>
  );
}

function SearchResults({
  search,
  onPick,
  query,
}: {
  search: ReturnType<typeof useInstrumentSearch>;
  onPick(instrument: Instrument): void;
  query: string;
}) {
  if (search.status === "searching") {
    return <Message>Searching…</Message>;
  }
  if (search.status === "error") {
    return (
      <Message tone="error">
        Search failed: {search.error}
        <br />
        <span className="text-ink-muted">Adjust the query or try again.</span>
      </Message>
    );
  }
  if (search.status === "no-results") {
    // Distinct from an error, and from an empty list with no explanation.
    return <Message>Nothing matches “{query.trim()}”.</Message>;
  }
  return <InstrumentTable instruments={search.instruments} onPick={onPick} />;
}

function Catalogue({ onPick }: { onPick(instrument: Instrument): void }) {
  const [page, setPage] = useState<InstrumentPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    setPage(null);
    setError(null);

    marketData
      .listInstruments(controller.signal)
      .then((result) => {
        if (!cancelled) setPage(result);
      })
      .catch((cause: unknown) => {
        if (cancelled || controller.signal.aborted) return;
        setError(cause instanceof Error ? cause.message : "could not list instruments");
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [attempt]);

  if (error) {
    return (
      <Message tone="error">
        {error}
        <button
          type="button"
          onClick={() => setAttempt((n) => n + 1)}
          className="ml-3 rounded border border-border px-2 py-0.5 text-xs text-ink hover:bg-panel-strong"
        >
          Retry
        </button>
      </Message>
    );
  }

  if (!page) {
    return <Message>Loading the catalogue…</Message>;
  }

  return (
    <>
      <p className="px-4 py-2 text-xs text-ink-muted">
        {page.count} instruments
        {page.truncated && (
          // The gateway walks a bounded slice of the provider's tree; a
          // partial catalogue must never read as the whole one.
          <span className="ml-2 text-warning">
            — the catalogue was cut short; search to reach anything not listed
          </span>
        )}
      </p>
      <InstrumentTable instruments={page.instruments} onPick={onPick} />
    </>
  );
}

function InstrumentTable({
  instruments,
  onPick,
}: {
  instruments: Instrument[];
  onPick(instrument: Instrument): void;
}) {
  return (
    <table className="w-full text-sm">
      <thead className="sticky top-0 bg-canvas text-left text-xs text-ink-muted">
        <tr>
          <th className="px-4 py-2 font-normal">Symbol</th>
          <th className="px-4 py-2 font-normal">Name</th>
          <th className="px-4 py-2 font-normal">Class</th>
          <th className="px-4 py-2 text-right font-normal">Bid</th>
          <th className="px-4 py-2 text-right font-normal">Ask</th>
          <th className="px-4 py-2 font-normal">Tradeable</th>
        </tr>
      </thead>
      <tbody>
        {instruments.map((instrument) => (
          <tr
            key={instrument.symbol}
            onClick={() => onPick(instrument)}
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onPick(instrument);
              }
            }}
            className="cursor-pointer border-t border-border hover:bg-panel focus:bg-panel focus:outline-none"
          >
            <td className="px-4 py-1.5 font-semibold text-ink">{instrument.symbol}</td>
            <td className="px-4 py-1.5 text-ink-secondary">{instrument.name}</td>
            <td className="px-4 py-1.5 text-ink-muted">{instrument.assetClass}</td>
            <td className="px-4 py-1.5 text-right text-ink-secondary">
              {instrument.bid ?? "—"}
            </td>
            <td className="px-4 py-1.5 text-right text-ink-secondary">
              {instrument.ask ?? "—"}
            </td>
            <td className="px-4 py-1.5">
              {instrument.tradeable ? (
                <span className="text-ink-muted">yes</span>
              ) : (
                // Charted all the same — only trading is off the table.
                <span className="text-warning" title="Not tradeable; it can still be charted.">
                  not tradeable
                </span>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Message({
  children,
  tone = "muted",
}: {
  children: React.ReactNode;
  tone?: "muted" | "error";
}) {
  return (
    <p className={`px-4 py-6 text-sm ${tone === "error" ? "text-critical" : "text-ink-muted"}`}>
      {children}
    </p>
  );
}
