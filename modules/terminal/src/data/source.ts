import type {
  Bar,
  Instrument,
  InstrumentPage,
  PairCoverage,
  Resolution,
  StreamEvent,
  TrackedPair,
} from "./types";

export interface HistoryRequest {
  symbol: string;
  resolution: Resolution;
  /** Inclusive, epoch seconds. */
  from: number;
  /** Exclusive, epoch seconds. */
  to: number;
}

/** One independently reachable back end behind the terminal's single source.
 *  There are two, and either can be down without the other: the archive keeps
 *  the candles, the gateway owns the instrument catalogue. Saying which is
 *  which is the whole reason this exists — "no data" and "no search" have
 *  different causes and different answers (design.md, Risks: "Archiwum staje
 *  się na ścieżce krytycznej wykresu"). */
export interface SourcePart {
  readonly id: string;
  /** What to call it where an operator can read it. */
  readonly label: string;
  /** What an operator loses while it is down, phrased for the indicator. Each
   *  adapter says its own: "unreachable" alone leaves the reader to guess
   *  whether the screen is empty or merely frozen. */
  readonly whenUnreachable: string;
  /** Resolves if the part answers, rejects with a `MarketDataError` otherwise.
   *  Carries no data of its own — it exists for the shell's connection
   *  indicator (terminal-shell spec, "Stan źródła danych jest widoczny
   *  globalnie"), polled independently of whatever charts happen to be
   *  subscribed at the time. */
  ping(signal: AbortSignal): Promise<void>;
}

/** Candles: a range read and a live subscription. Implemented by the archive.
 *
 *  `history` is the range read; it is not how a chart gets its series. That
 *  comes from `subscribe`, whose first message carries the snapshot — see
 *  `StreamEvent`. */
export interface CandleSource extends SourcePart {
  history(request: HistoryRequest, signal: AbortSignal): Promise<Bar[]>;

  /** Subscribe to one (symbol, resolution) pair. `sink` receives every event —
   *  the opening snapshot, bars, status, error — for that pair until the
   *  returned cleanup function is called. Multiple subscribers to the same pair
   *  MUST share one underlying connection (terminal-market-data spec) — that
   *  sharing lives in the source implementation, not in callers. */
  subscribe(
    symbol: string,
    resolution: Resolution,
    sink: (event: StreamEvent) => void,
  ): () => void;
}

/** The instrument catalogue, which stays with `capital-gateway` because that is
 *  who owns it. The archive does not pretend to own things it does not have. */
export interface InstrumentSource extends SourcePart {
  searchInstruments(query: string, signal: AbortSignal): Promise<Instrument[]>;

  listInstruments(signal: AbortSignal): Promise<InstrumentPage>;
}

/**
 * What every view reads through: one interface, one instance, whatever sits
 * behind it. Behind it today are two back ends — candles from the archive,
 * instruments from the gateway — and no view knows that or may find out
 * (terminal-market-data spec, "Świece i instrumenty idą z różnych miejsc").
 *
 * The composition lives in `marketData.ts`; views take the instance it exports
 * and never a constructor.
 */
export interface MarketDataSource
  extends Pick<CandleSource, "history" | "subscribe">,
    Pick<InstrumentSource, "searchInstruments" | "listInstruments"> {
  /** The back ends this source is made of, so the shell can say which one is
   *  unreachable instead of calling the whole terminal offline. */
  readonly parts: readonly SourcePart[];
}

/** Managing what the archive collects. Not part of `MarketDataSource`: this is
 *  administration rather than reading market data, and only the archive panel
 *  has any business with it. */
export interface ArchiveAdmin {
  listPairs(signal: AbortSignal): Promise<TrackedPair[]>;

  /** Starts collection. Refused — never silently ignored — when the ceiling is
   *  full or the gateway will not serve the pair. */
  trackPair(symbol: string, resolution: Resolution, signal: AbortSignal): Promise<TrackedPair>;

  /** Stops collection. The candles already collected stay. */
  untrackPair(symbol: string, resolution: Resolution, signal: AbortSignal): Promise<void>;

  coverage(symbol: string, resolution: Resolution, signal: AbortSignal): Promise<PairCoverage>;
}
