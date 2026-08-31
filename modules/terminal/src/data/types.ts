/**
 * The terminal's own vocabulary, not the wire shapes of whoever answers: the adapters (`archive.ts`,
 * `gatewaySource.ts`) are the only places that see a payload (design.md, "Terminal składa jedno źródło z dwóch").
 */

export const RESOLUTIONS = [
  "MINUTE",
  "MINUTE_5",
  "MINUTE_15",
  "MINUTE_30",
  "HOUR",
  "HOUR_4",
  "DAY",
  "WEEK",
] as const;

export type Resolution = (typeof RESOLUTIONS)[number];

// Deliberately absent: a per-resolution period length. A daily candle starts at the venue's session open
// rather than UTC midnight, so computing one locally would be wrong exactly where it mattered (design.md).

export type AssetClass =
  | "SHARES"
  | "INDICES"
  | "CRYPTO"
  | "CURRENCIES"
  | "COMMODITIES"
  | "OTHER";

export interface Instrument {
  symbol: string;
  name: string;
  assetClass: AssetClass;
  tradeable: boolean;
  bid: number | null;
  ask: number | null;
}

export interface InstrumentPage {
  instruments: Instrument[];
  count: number;
  /** True when the catalogue walk was cut short — a partial list must never be
   *  mistaken for a complete one (terminal-instruments spec). */
  truncated: boolean;
}

/** One candle, in the terminal's one time representation: epoch seconds at the start of the period, which is
 *  what lightweight-charts indexes by. REST's ISO `ts` is converted on the way in — see time.ts. */
export interface Bar {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  /** null means "this source doesn't carry volume here" (e.g. the WebSocket
   *  feed), never zero. */
  volume: number | null;
  /** True while this bar is still being assembled from quotes and can still
   *  change — see terminal-market-data spec, "Świeca w budowie jest oznaczona
   *  jako niepewna". */
  forming: boolean;
}

export type ConnectionState = "connecting" | "connected" | "reconnecting" | "closed";

export type StreamEvent =
  /** The series as it stands, delivered first and again after every reconnect: the archive reads it holding
   *  the room still and attaches the subscriber before letting go, so no bar falls between or arrives twice. */
  | { kind: "snapshot"; bars: Bar[]; forming: Bar | null }
  | { kind: "bar"; bar: Bar }
  | { kind: "status"; state: ConnectionState }
  | { kind: "error"; message: string };

export type MarketDataErrorKind =
  | "not-found"
  | "unsupported-resolution"
  /** The archive understood the request and declined it — a ceiling reached, a
   *  symbol it will not take on. Distinct from a failure: retrying unchanged
   *  gets the same answer, and the message says what to change. */
  | "refused"
  /** The archive answered, but on behalf of something behind it that did not.
   *  Retrying is worth doing; nothing about the request is wrong. */
  | "upstream"
  /** Not you, rather than not that: retrying unchanged cannot help, the operator has to sign in. Kept apart
   *  from `unreachable` because showing this as that sends somebody to Azure for what a sign-in would fix. */
  | "unauthenticated"
  | "unreachable"
  | "unknown";

/** What a failed request or a dead subscription tells the UI. Never carries a
 *  credential and never a raw network error — terminal-market-data spec,
 *  "Zapytanie o dane nazywa swoją porażkę". */
export class MarketDataError extends Error {
  readonly kind: MarketDataErrorKind;

  constructor(kind: MarketDataErrorKind, message: string) {
    super(message);
    this.name = "MarketDataError";
    this.kind = kind;
  }
}

// Only the archive panel speaks these; the chart never sees one. Here rather than beside the panel because
// they are vocabulary the data layer hands out, not shapes a view invented.

/** Whether data is actually arriving for a pair. Being on the list proves nothing — a subscription can die
 *  without a sound — and `unknown` is a third answer: behind, with nobody able to say whether the market is open. */
export type CollectionState =
  | "never_collected"
  | "collecting"
  | "stalled"
  | "market_closed"
  | "unknown";

export interface TrackedPair {
  symbol: string;
  resolution: Resolution;
  /** Epoch seconds, like every other instant here. */
  addedAt: number;
  /** The moment history for this pair is meant to reach back to. */
  collectFrom: number;
  /** The oldest period collected — how far back the data reaches, which is not
   *  `collectFrom`, where it was asked to reach. null when nothing has been
   *  collected yet. */
  earliestCandle: number | null;
  /** The newest period collected, or null when nothing has been yet. */
  latestCandle: number | null;
  collection: CollectionState;
  /** How many candles are collected for this pair. Zero for a pair that has
   *  collected nothing, never absent. */
  candleCount: number;
  /** A rough estimate of the storage those candles take, derived from
   *  `candleCount` the same way a job's price is (`market-data-api` spec,
   *  "Śledzone pary są zarządzalne przez kontrakt"). */
  estimatedBytes: number;
}

/** A stretch of time the archive has actually verified for a pair — which is
 *  what makes an empty period an answer rather than an absence. */
export interface CoverageRange {
  from: number;
  to: number;
  /** True when the provider has nothing older than `from`, so this is as far
   *  back as the pair can ever reach. */
  historyEnded: boolean;
}

export interface PairCoverage {
  symbol: string;
  resolution: Resolution;
  ranges: CoverageRange[];
  /** The oldest moment worth asking the provider about. null means the end of
   *  its history has not been reached yet — never "there is no limit". */
  earliestReachable: number | null;
}

// Only the Instruments wizard and the Data History tab speak these. `market-data-jobs` spec: a job is the
// decision, a chunk is one pair, one window, one gateway request.

/** One chunk's life. `interrupted` means the module restarted while this
 *  chunk was queued or in flight — never a failure of the chunk itself. */
export type ChunkState = "pending" | "running" | "done" | "failed" | "skipped" | "interrupted";

export interface Chunk {
  id: number;
  symbol: string;
  resolution: Resolution;
  /** Epoch seconds, half-open: `chunkStart` inclusive, `chunkEnd` exclusive. */
  chunkStart: number;
  chunkEnd: number;
  state: ChunkState;
  attempt: number;
  candlesWritten: number;
  requests: number;
  /** Why this chunk failed, named — null when it did not. */
  failure: string | null;
  startedAt: number | null;
  finishedAt: number | null;
}

/** Never stored, always derived from a job's chunks — see `market-data-jobs`
 *  spec, "Historia zleceń przeżywa restart". `running` covers a chunk merely
 *  queued, not only one actually in flight: a runner is what makes `pending`
 *  mean "about to happen" rather than "stuck". */
export type JobStatus = "running" | "succeeded" | "partial" | "failed" | "interrupted";

/** One job, narrowed to one pair it touched — what the Data History tab reads.
 *  A job spanning four pairs is four of these, each with only that pair's
 *  chunks. */
export interface JobPairView {
  jobId: number;
  symbol: string;
  resolution: Resolution;
  createdAt: number;
  requestedFrom: number;
  attempt: number;
  status: JobStatus;
  chunksDone: number;
  chunksTotal: number;
  candlesWritten: number;
  /** Epoch seconds: when something last happened for this pair — a chunk
   *  starting counts, not only one settling. The job's own creation while
   *  nothing has been claimed yet. Progress and candle counts read the same for
   *  a job that is working and one that is stuck; this is what separates them. */
  lastActivityAt: number;
  chunks: Chunk[];
}

/** A whole job — every pair and chunk it covers. What the wizard's acceptance
 *  dialog gets back, and what a single job reads as. */
export interface Job {
  id: number;
  createdAt: number;
  requestedFrom: number;
  attempt: number;
  status: JobStatus;
  chunksDone: number;
  chunksTotal: number;
  candlesWritten: number;
  /** Epoch seconds — see `JobPairView.lastActivityAt`, across every pair. */
  lastActivityAt: number;
  /** The pair a chunk is presently in flight for, or null when nothing is
   *  running right now. */
  runningPair: { symbol: string; resolution: Resolution } | null;
  chunks: Chunk[];
}

/** What one pair in a prospective job would cost — before anything is
 *  fetched. `market-data-jobs` spec, "Zlecenie da się wycenić przed jego
 *  uruchomieniem". */
export interface PairEstimate {
  symbol: string;
  resolution: Resolution;
  /** What the requested start was actually clipped to; null when the symbol
   *  is unknown to the gateway. */
  effectiveFrom: number | null;
  /** True when `effectiveFrom` differs from what was requested — the
   *  provider's own history, or what the archive already holds, fell short. */
  clipped: boolean;
  estimatedCandles: number;
  estimatedBytes: number;
  /** True when the gateway does not know this symbol at all. */
  unknown: boolean;
}

export interface JobEstimate {
  pairs: PairEstimate[];
  totalEstimatedCandles: number;
  totalEstimatedBytes: number;
}

/** One pair as named in a request — dodawany, wyceniany. */
export interface PairRequest {
  symbol: string;
  resolution: Resolution;
}

/** One pair's outcome from adding several at once — a refusal for one must
 *  never be indistinguishable from silence about it. */
export interface TrackedPairResult {
  symbol: string;
  resolution: Resolution;
  pair: TrackedPair | null;
  /** Why this pair was refused; null when it was accepted. */
  refused: string | null;
}

export interface TrackPairsResult {
  results: TrackedPairResult[];
  /** The backfill job covering the accepted pairs, or null when nothing
   *  needed fetching. */
  jobId: number | null;
}

// Only the Instruments tab's Delete confirmation and Data History's timeline speak this
// (`market-data-tracking` spec, "Skasowanie zostaje odnotowane").

/** The trace one skasowanie leaves — what it removed, kept after the data
 *  itself is gone. `removedFrom`/`removedTo` are null together when the pair
 *  had never collected anything before it was deleted. */
export interface PairDeletion {
  symbol: string;
  resolution: Resolution;
  deletedAt: number;
  candlesRemoved: number;
  removedFrom: number | null;
  removedTo: number | null;
}

// Only the chart and its picker speak these. The catalogue is data, not a hand-kept list: a new archive
// indicator shows up without a terminal release (`market-data-indicators` spec, "Katalog wystarcza…").

export type IndicatorParamType = "int" | "float";

export interface IndicatorParam {
  name: string;
  type: IndicatorParamType;
  default: number;
  min: number;
  max: number;
}

/** `label` is a template like `"EMA {period}"` — a caller fills in `{period}` from the
 *  chosen params itself; the archive never renders a string for it. */
export interface IndicatorLineSpec {
  key: string;
  label: string;
  /** Overrides the entry's own `render.style` for this one line — MACD's histogram
   *  line inside an otherwise line-style entry. `null` means: use `render.style`. */
  style: IndicatorStyle | null;
}

export type IndicatorPane = "price" | "own";
export type IndicatorStyle = "line" | "dots" | "histogram";
export type IndicatorScale = "price" | "own" | "fixed";

export interface IndicatorRender {
  pane: IndicatorPane;
  style: IndicatorStyle;
  scale: IndicatorScale;
  /** Whether this indicator's own values may widen the price axis it shares — off for
   *  one whose values are not comparable to price, so a long average sitting far from
   *  the current price cannot flatten the candles it is drawn over. */
  autoscale: boolean;
  range: [number, number] | null;
  /** Reference lines to draw for this indicator, e.g. 30/70 for RSI. */
  levels: number[];
}

export type IndicatorOutputShape = "lines" | "markers" | "zones" | "levels";
export type IndicatorWarmupKind = "fixed" | "decay";

/** One row of the catalogue — everything the picker needs to offer this indicator and
 *  everything the chart needs to draw it, without either knowing it by name. */
export interface IndicatorCatalogueEntry {
  id: string;
  name: string;
  /** Names an operator might search by that are not `id` — never the vocabulary of
   *  one trading school baked into the identifier itself. */
  aliases: string[];
  group: string;
  output: IndicatorOutputShape;
  params: IndicatorParam[];
  lines: IndicatorLineSpec[];
  render: IndicatorRender;
  warmupKind: IndicatorWarmupKind;
}

export interface IndicatorCatalogue {
  algorithmVersion: number;
  indicators: IndicatorCatalogueEntry[];
}

/** One indicator as the operator chose it — never the resolved defaults, so a catalogue
 *  update that changes a default does not silently change what a saved slot draws.
 *  What `terminal-grid` spec's slot state actually stores. */
export interface IndicatorSelection {
  /** This instance's identity, handed out when it is added and never derived from what
   *  it holds. One catalogue entry may be chosen more than once, and a second instance
   *  is born carrying the first one's default params — a key computed from `id` and
   *  `params` would collide at that moment (design.md, "Instancja ma własny klucz"). */
  key: string;
  id: string;
  params: Record<string, number>;
  /** A palette token name (`--color-indicator-5`), never a hex string: the token is what
   *  follows the theme, and a saved slot outlives whatever the token resolved to when it
   *  was chosen. Null means the chart assigns one from its own cycle, as it always did. */
  color: string | null;
}

/** A one-off request to show a fragment of a chart's time axis — epoch seconds,
 *  exactly one of the three shapes filled: a `from`/`to` range, an `around`/`bars`
 *  point, or `lastBars` alone. Not part of a saved selection — it is what the chart
 *  should be shown next, not something it remembers having. */
export interface ChartFocusRequest {
  from: number | null;
  to: number | null;
  around: number | null;
  bars: number | null;
  lastBars: number | null;
}

/** The visible span, in the drawn series' own bar times (epoch seconds) — what a caller
 *  needing to know "what is the operator looking at" reads, without touching the chart
 *  library itself. */
export interface VisibleTimeRange {
  from: number;
  to: number;
}

let fallbackKeys = 0;

/** A fresh instance identity. `randomUUID` where there is one; a counter where there is
 *  not, since the key only has to be unique within one operator's selections. */
export function newIndicatorSelectionKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? `indicator-${(fallbackKeys += 1)}`;
}

export interface IndicatorMarker {
  time: number;
  label: string;
  price: number | null;
}

/** `to` and the two "did price arrive here" instants are null for a zone the
 *  requested range never resolved — `terminal-chart` spec, "Strefy i poziomy
 *  rysują się jako obszary, nie jako linie serii". */
export interface IndicatorZone {
  from: number;
  to: number | null;
  top: number;
  bottom: number;
  direction: "bullish" | "bearish" | null;
  touchedAt: number | null;
  filledAt: number | null;
}

export interface IndicatorLevel {
  from: number;
  price: number;
  label: string | null;
  /** How many extrema support this level — `level_clusters`' weight. Null for a
   *  level that carries none, e.g. a pivot or a previous-period edge. */
  count: number | null;
}

/** One requested indicator's answer. Exactly one of `lines`/`markers`/`zones`/`levels`
 *  is set — the one its catalogue entry's `output` names. */
export interface IndicatorResult {
  id: string;
  /** Resolved params — defaults filled in, so a chart reading this back never has to
   *  consult the catalogue to know what it is drawing. */
  params: Record<string, number>;
  /** Null for a result carrying an error instead of an answer. */
  warmupBars: number | null;
  /** False when the archive did not hold enough history before the requested range
   *  for this result to be trusted yet. Says nothing about `error` — an unsettled
   *  value is still a value. */
  settled: boolean;
  /** Why this one indicator could not be computed, when the archive does not hold the
   *  series it needs. Set instead of a shape, never beside one: an empty `zones` means
   *  the range held none, which is a different claim and must not be drawn the same.
   *  A request the archive refuses outright fails the whole read instead. */
  error: string | null;
  lines: Record<string, (number | null)[]> | null;
  markers: IndicatorMarker[] | null;
  zones: IndicatorZone[] | null;
  levels: IndicatorLevel[] | null;
}

/** `POST /indicators/{symbol}` — one or more indicators, on one shared time axis. */
export interface IndicatorsResult {
  symbol: string;
  resolution: Resolution;
  derived: boolean;
  algorithmVersion: number;
  /** Epoch seconds, shared by every result's `lines`/`markers`/`zones`/`levels`. */
  times: number[];
  results: IndicatorResult[];
}
