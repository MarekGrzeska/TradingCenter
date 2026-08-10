/**
 * The terminal's own vocabulary — not the wire shapes of whoever answers. The
 * adapters (`archive.ts` for candles, `gatewaySource.ts` for instruments) are
 * the only places that ever see a payload; every other module speaks these
 * types. See design.md, "Terminal składa jedno źródło z dwóch".
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

// Deliberately absent: a per-resolution period length. Nothing here needs to
// know how long a candle lasts — timestamps come from the source, and a daily
// candle starts at the venue's session open rather than UTC midnight, so
// computing one locally would be wrong exactly where it mattered. See
// design.md, Risks: "`DAY` i `WEEK` nie mają stałej długości okresu."

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

/** One candle, in the terminal's one time representation: epoch seconds at the
 *  start of the period, matching what lightweight-charts indexes by and what the
 *  WebSocket already sends. REST's ISO `ts` is converted on the way in — see
 *  time.ts — so nothing downstream of the source implementations ever sees an
 *  ISO string. */
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
  /** The series as it stands, always the first thing a subscription delivers
   *  and delivered again after every reconnect. It is what replaced the
   *  terminal's own history-plus-stream stitching: the archive reads it while
   *  holding the room still and attaches the subscriber before letting go, so
   *  no bar can fall between the snapshot and the changes, and none can arrive
   *  twice (market-data README, "The subscription"). */
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
  /** Not you, rather than not that. Nothing about the request was wrong and
   *  retrying it unchanged cannot help — the operator has to sign in. Kept
   *  apart from `unreachable` for exactly that reason: one is a source that is
   *  down and the other is a source that is fine and does not know who is
   *  asking, and showing the second as the first sends somebody looking at
   *  Azure for a problem that a sign-in would fix. */
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

// --- what the archive is collecting, and how far it reaches ---
//
// Only the archive panel speaks these; the chart never sees one. They are here
// rather than next to the panel because they are vocabulary the data layer
// hands out, not shapes a view invented.

/** Whether data is actually arriving for a pair, as far as the archive can
 *  tell. Being on the list proves nothing — a subscription can die without a
 *  sound, and the only symptom is a series that stops growing. `unknown` is a
 *  third answer on purpose: behind, with nobody able to say whether the market
 *  is open. */
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

// --- collection jobs: dociąganie historii, jako coś operator zleca i śledzi ---
//
// Only the Instruments tab's wizard and the Data History tab speak these — the
// chart never sees one. `market-data-jobs` spec: a job is the decision, a
// chunk is one pair, one window, one gateway request.

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

// --- deletion: kasowanie, a decision that removes data, not just a decision ---
//
// Only the Instruments tab (the Delete confirmation) and Data History tab (the
// combined timeline) speak this. `market-data-tracking` spec, "Skasowanie
// zostaje odnotowane".

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
