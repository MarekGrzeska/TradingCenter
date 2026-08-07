import type { Bar, Instrument, InstrumentPage, Resolution, StreamEvent } from "./types";

export interface HistoryRequest {
  symbol: string;
  resolution: Resolution;
  /** How many candles to reach back for. Capped and paged by the source, not
   *  the caller — see capital-gateway's `/history`. */
  count: number;
}

/** One interface, swappable implementations. `gatewaySource` is the only one
 *  today; a candle-store implementation slots in later the same way, without
 *  the chart, the grid or the search knowing — see design.md. Views read the
 *  single instance exported by `marketData.ts`, never a constructor. */
export interface MarketDataSource {
  readonly id: "gateway";

  searchInstruments(query: string, signal: AbortSignal): Promise<Instrument[]>;

  listInstruments(signal: AbortSignal): Promise<InstrumentPage>;

  history(request: HistoryRequest, signal: AbortSignal): Promise<Bar[]>;

  /** Resolves if the source is reachable, rejects with a `MarketDataError`
   *  otherwise. Carries no data of its own — it exists for the shell's global
   *  connection indicator (terminal-shell spec, "Stan źródła danych jest
   *  widoczny globalnie"), polled independently of whatever charts happen to
   *  be subscribed at the time. */
  ping(signal: AbortSignal): Promise<void>;

  /** Subscribe to one (symbol, resolution) pair. `sink` receives every event —
   *  bars, quotes, status, error — for that pair until the returned cleanup
   *  function is called. Multiple subscribers to the same pair MUST share one
   *  underlying connection (terminal-market-data spec) — that sharing lives in
   *  the source implementation, not in callers. */
  subscribe(
    symbol: string,
    resolution: Resolution,
    sink: (event: StreamEvent) => void,
  ): () => void;
}
