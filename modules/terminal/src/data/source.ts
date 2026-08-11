import type {
  AssetClass,
  Bar,
  IndicatorCatalogue,
  IndicatorSelection,
  IndicatorsResult,
  Instrument,
  InstrumentPage,
  Job,
  JobEstimate,
  JobPairView,
  PairCoverage,
  PairDeletion,
  PairRequest,
  Resolution,
  StreamEvent,
  TrackedPair,
  TrackPairsResult,
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
  searchInstruments(
    query: string,
    signal: AbortSignal,
    assetClass?: AssetClass,
  ): Promise<Instrument[]>;

  /** `assetClass` narrows the walk to one class and lifts the gateway's own
   *  node budget for it — a wizard's second autocomplete needs "every
   *  instrument in this class", not a catalogue slice cut short by a bound
   *  sized for browsing everything. */
  listInstruments(signal: AbortSignal, assetClass?: AssetClass): Promise<InstrumentPage>;

  /** The classes the gateway describes instruments with — the wizard's first
   *  autocomplete, sourced rather than hand-copied so it cannot drift from
   *  what the gateway actually knows. */
  listAssetClasses(signal: AbortSignal): Promise<AssetClass[]>;
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
 *  administration rather than reading market data, and only the Instruments
 *  tab and Data History tab have any business with it. */
export interface ArchiveAdmin {
  listPairs(signal: AbortSignal): Promise<TrackedPair[]>;

  /** Starts collection for one or more pairs as a single decision. Each pair
   *  is refused independently — never silently ignored — when the ceiling is
   *  full or the gateway will not serve it; a refusal for one never withholds
   *  the pairs that were fine. `collectFrom` null means the configured
   *  default depth. */
  trackPairs(
    pairs: PairRequest[],
    collectFrom: number | null,
    signal: AbortSignal,
  ): Promise<TrackPairsResult>;

  /** Stops collection and irreversibly removes the pair's candles and
   *  coverage. Resolves with what was removed — a count and, unless nothing
   *  had ever been collected, the range it covered — which is what a
   *  confirmation reports back once it is done. */
  deletePair(symbol: string, resolution: Resolution, signal: AbortSignal): Promise<PairDeletion>;

  coverage(symbol: string, resolution: Resolution, signal: AbortSignal): Promise<PairCoverage>;

  /** Every recorded deletion, newest first. `symbol`/`resolution` narrow to
   *  one pair, the same shape `listJobs` narrows by, since the combined
   *  history reads both. */
  listDeletions(
    symbol: string | null,
    resolution: Resolution | null,
    signal: AbortSignal,
  ): Promise<PairDeletion[]>;

  /** Prices a prospective job without creating it or tracking anything —
   *  what the wizard's acceptance dialog reads before the operator commits. */
  estimateJob(pairs: PairRequest[], collectFrom: number, signal: AbortSignal): Promise<JobEstimate>;

  /** Every job, one row per pair it touched, newest first. `symbol`/
   *  `resolution` narrow to one pair; both null reads every job. */
  listJobs(
    symbol: string | null,
    resolution: Resolution | null,
    signal: AbortSignal,
  ): Promise<JobPairView[]>;

  /** One job, whole — every pair and chunk it covers. */
  readJob(jobId: number, signal: AbortSignal): Promise<Job>;

  /** Retries a job's failed and interrupted chunks as a new attempt of the
   *  same job. Rejects with a `MarketDataError` of kind `"refused"` when
   *  there is nothing to retry. */
  retryJob(jobId: number, signal: AbortSignal): Promise<Job>;

  /** Removes a job from the collection history, with every chunk it covers.
   *  Deletes no candle — the data the job collected stays archived, which is
   *  what separates this from `deletePair`. Rejects with a `MarketDataError`
   *  of kind `"refused"` while any of its chunks is still pending or
   *  running. */
  deleteJob(jobId: number, signal: AbortSignal): Promise<void>;
}

/** Indicators: the catalogue every picker builds from, and the computation behind it.
 *  Not part of `MarketDataSource` — only the chart and its picker have any business
 *  with this, the same way `ArchiveAdmin` is narrowed away from the views that only
 *  read candles. */
export interface IndicatorSource {
  /** Every indicator this source can compute, and how to draw each one. A consumer
   *  builds its whole picker from this and never needs to know an indicator by name
   *  beforehand (`market-data-indicators` spec, "Katalog wystarcza do zbudowania
   *  wybieraka"). */
  indicatorCatalogue(signal: AbortSignal): Promise<IndicatorCatalogue>;

  /** One or more indicators over a range, on one shared time axis. Rejects with a
   *  `MarketDataError` of kind `"refused"` for an unknown id, an out-of-range param,
   *  or a request past the source's ceiling — each named in the message. */
  computeIndicators(
    symbol: string,
    resolution: Resolution,
    from: number,
    to: number,
    specs: IndicatorSelection[],
    signal: AbortSignal,
  ): Promise<IndicatorsResult>;
}
