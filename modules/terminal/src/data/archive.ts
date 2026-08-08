import { jsonClient } from "./http";
import { SocketHub } from "./socketHub";
import { parseIsoToEpochSeconds } from "./time";
import { MarketDataError } from "./types";
import type {
  Bar,
  Chunk,
  ChunkState,
  CollectionState,
  Job,
  JobEstimate,
  JobPairView,
  JobStatus,
  PairCoverage,
  PairEstimate,
  PairRequest,
  Resolution,
  StreamEvent,
  TrackedPair,
  TrackedPairResult,
  TrackPairsResult,
} from "./types";
import type { ArchiveAdmin, CandleSource, HistoryRequest } from "./source";

/**
 * The candle side of the terminal's source: `market-data`, over its HTTP
 * contract and its subscription.
 *
 * The subscription is why this module exists in the shape it does. The gateway
 * serves changes and nothing else, so a chart reading it had to fetch a history
 * and splice the stream onto it, and between the two lay a window in which a
 * candle could close unseen. The archive's first message is the series itself,
 * read while its room is held still — so there is nothing to splice, nothing to
 * fetch after a reconnect, and no duplicate to filter (design.md, "Archiwum
 * jest dla terminala jedynym źródłem świec i strumienia").
 *
 * `market-data`'s wire shapes (snake_case, per its OpenAPI schema) are private
 * to this file. Nothing outside it ever sees one.
 */

interface RawCandle {
  time: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
}

interface RawCandles {
  symbol: string;
  resolution: string;
  price_side: string;
  derived: boolean;
  candles: RawCandle[];
  uncovered: Array<{ from: string; to: string }>;
}

/** The subscription's candle, which is the archive's own storage shape rather
 *  than the range read's — `period_start` where the other says `time`, and a
 *  `forming` flag the range read has no use for. */
interface RawStreamCandle {
  symbol: string;
  resolution: string;
  period_start: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
  forming: boolean;
}

interface RawCoverage {
  symbol: string;
  resolution: string;
  ranges: Array<{ from: string; to: string; history_ended: boolean }>;
  earliest_reachable: string | null;
}

interface RawTrackedPair {
  symbol: string;
  resolution: string;
  added_at: string;
  collect_from: string;
  earliest_candle: string | null;
  latest_candle: string | null;
  collection: string;
}

interface RawChunk {
  id: number;
  symbol: string;
  resolution: string;
  chunk_start: string;
  chunk_end: string;
  state: string;
  attempt: number;
  candles_written: number;
  requests: number;
  failure: string | null;
  started_at: string | null;
  finished_at: string | null;
}

interface RawJobPairView {
  job_id: number;
  symbol: string;
  resolution: string;
  created_at: string;
  requested_from: string;
  attempt: number;
  status: string;
  chunks_done: number;
  chunks_total: number;
  candles_written: number;
  chunks: RawChunk[];
}

interface RawJob {
  id: number;
  created_at: string;
  requested_from: string;
  attempt: number;
  status: string;
  chunks_done: number;
  chunks_total: number;
  candles_written: number;
  running_pair: { symbol: string; resolution: string } | null;
  chunks: RawChunk[];
}

interface RawPairEstimate {
  symbol: string;
  resolution: string;
  effective_from: string | null;
  clipped: boolean;
  estimated_candles: number;
  estimated_bytes: number;
  unknown: boolean;
}

interface RawJobEstimate {
  pairs: RawPairEstimate[];
  total_estimated_candles: number;
  total_estimated_bytes: number;
}

interface RawTrackedPairResult {
  symbol: string;
  resolution: string;
  pair: RawTrackedPair | null;
  refused: string | null;
}

interface RawTrackPairsResult {
  results: RawTrackedPairResult[];
  job_id: number | null;
}

/** A candle missing any OHLC field (the provider reports this for a period with
 *  no trade) can't become a `Bar` — `Bar`'s fields are non-nullable by design,
 *  so such a candle is dropped rather than faked with a zero. */
function toBar(raw: RawCandle | RawStreamCandle, forming: boolean): Bar | null {
  if (raw.open === null || raw.high === null || raw.low === null || raw.close === null) {
    return null;
  }
  return {
    time: parseIsoToEpochSeconds("time" in raw ? raw.time : raw.period_start),
    open: raw.open,
    high: raw.high,
    low: raw.low,
    close: raw.close,
    volume: raw.volume,
    forming,
  };
}

function mapTrackedPair(raw: RawTrackedPair): TrackedPair {
  return {
    symbol: raw.symbol,
    resolution: raw.resolution as Resolution,
    addedAt: parseIsoToEpochSeconds(raw.added_at),
    collectFrom: parseIsoToEpochSeconds(raw.collect_from),
    earliestCandle:
      raw.earliest_candle === null ? null : parseIsoToEpochSeconds(raw.earliest_candle),
    latestCandle: raw.latest_candle === null ? null : parseIsoToEpochSeconds(raw.latest_candle),
    collection: raw.collection as CollectionState,
  };
}

function mapChunk(raw: RawChunk): Chunk {
  return {
    id: raw.id,
    symbol: raw.symbol,
    resolution: raw.resolution as Resolution,
    chunkStart: parseIsoToEpochSeconds(raw.chunk_start),
    chunkEnd: parseIsoToEpochSeconds(raw.chunk_end),
    state: raw.state as ChunkState,
    attempt: raw.attempt,
    candlesWritten: raw.candles_written,
    requests: raw.requests,
    failure: raw.failure,
    startedAt: raw.started_at === null ? null : parseIsoToEpochSeconds(raw.started_at),
    finishedAt: raw.finished_at === null ? null : parseIsoToEpochSeconds(raw.finished_at),
  };
}

function mapJobPairView(raw: RawJobPairView): JobPairView {
  return {
    jobId: raw.job_id,
    symbol: raw.symbol,
    resolution: raw.resolution as Resolution,
    createdAt: parseIsoToEpochSeconds(raw.created_at),
    requestedFrom: parseIsoToEpochSeconds(raw.requested_from),
    attempt: raw.attempt,
    status: raw.status as JobStatus,
    chunksDone: raw.chunks_done,
    chunksTotal: raw.chunks_total,
    candlesWritten: raw.candles_written,
    chunks: raw.chunks.map(mapChunk),
  };
}

function mapJob(raw: RawJob): Job {
  return {
    id: raw.id,
    createdAt: parseIsoToEpochSeconds(raw.created_at),
    requestedFrom: parseIsoToEpochSeconds(raw.requested_from),
    attempt: raw.attempt,
    status: raw.status as JobStatus,
    chunksDone: raw.chunks_done,
    chunksTotal: raw.chunks_total,
    candlesWritten: raw.candles_written,
    runningPair: raw.running_pair
      ? { symbol: raw.running_pair.symbol, resolution: raw.running_pair.resolution as Resolution }
      : null,
    chunks: raw.chunks.map(mapChunk),
  };
}

function mapPairEstimate(raw: RawPairEstimate): PairEstimate {
  return {
    symbol: raw.symbol,
    resolution: raw.resolution as Resolution,
    effectiveFrom: raw.effective_from === null ? null : parseIsoToEpochSeconds(raw.effective_from),
    clipped: raw.clipped,
    estimatedCandles: raw.estimated_candles,
    estimatedBytes: raw.estimated_bytes,
    unknown: raw.unknown,
  };
}

function mapJobEstimate(raw: RawJobEstimate): JobEstimate {
  return {
    pairs: raw.pairs.map(mapPairEstimate),
    totalEstimatedCandles: raw.total_estimated_candles,
    totalEstimatedBytes: raw.total_estimated_bytes,
  };
}

function mapTrackPairsResult(raw: RawTrackPairsResult): TrackPairsResult {
  return {
    results: raw.results.map(
      (result): TrackedPairResult => ({
        symbol: result.symbol,
        resolution: result.resolution as Resolution,
        pair: result.pair === null ? null : mapTrackedPair(result.pair),
        refused: result.refused,
      }),
    ),
    jobId: raw.job_id,
  };
}

/** What each refusal means, said once. The archive is careful about its status
 *  codes and each of them asks something different of whoever reads it: 409 is
 *  a ceiling to raise deliberately, 422 a pair it will not take on, and 502/504
 *  the *gateway* being unreachable — which is worth retrying and says nothing
 *  about the archive itself. */
function mapStatus(status: number, detail: string): MarketDataError {
  if (status === 404) return new MarketDataError("not-found", detail);
  if (status === 409 || status === 422) return new MarketDataError("refused", detail);
  if (status === 502 || status === 504) return new MarketDataError("upstream", detail);
  return new MarketDataError("unknown", detail);
}

/** Every instant on the wire is ISO; every instant in the terminal is epoch
 *  seconds (types.ts, `Bar.time`). This is the only direction that needs
 *  spelling out — the other one is `parseIsoToEpochSeconds`. */
function toIso(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toISOString();
}

/** The archive's subscription, in the terminal's vocabulary.
 *
 *  A frame whose `kind` is unknown yields nothing: a message the archive adds
 *  one day must not break a chart that predates it. */
export function translateMessage(raw: string): StreamEvent[] {
  let message: Record<string, unknown>;
  try {
    message = JSON.parse(raw);
  } catch {
    return [];
  }

  if (message.kind === "snapshot") {
    const candles = (message.candles ?? []) as RawStreamCandle[];
    const rawForming = (message.forming ?? null) as RawStreamCandle | null;
    const bars: Bar[] = [];
    for (const candle of candles) {
      const settled = toBar(candle, false);
      if (settled) bars.push(settled);
    }
    return [
      { kind: "snapshot", bars, forming: rawForming ? toBar(rawForming, true) : null },
    ];
  }

  if (message.kind === "candle") {
    const candle = message.candle as RawStreamCandle | undefined;
    if (!candle) return [];
    // `forming` travels on the candle rather than the frame: one message kind
    // covers both states, marked, because a consumer upserts by period start
    // and two kinds would only make it reconcile them itself.
    const bar = toBar(candle, Boolean(candle.forming));
    return bar ? [{ kind: "bar", bar }] : [];
  }

  return [];
}

export type ArchiveSource = CandleSource & ArchiveAdmin;

/** How long the "why did that socket not open" question may take before the
 *  answer stops being worth waiting for. Short, because a chart is sitting on
 *  it and the fallback — keep retrying — is the safe one. */
const DIAGNOSIS_TIMEOUT_MS = 5_000;

/**
 * What the tracked-pair list says about a subscription that would not open, or
 * `null` if it says nothing that should stop the retrying.
 *
 * Split out from the request that fetches the list because this is the part
 * with a judgement in it: a pair absent from the list is a settled answer, and
 * everything else — including a list that could not be read — is not.
 */
export function readRefusalFromPairs(
  pairs: TrackedPair[],
  symbol: string,
  resolution: Resolution,
): string | null {
  const tracked = pairs.some(
    (pair) => pair.symbol === symbol && pair.resolution === resolution,
  );
  if (tracked) return null;
  return `${symbol} ${resolution} is not being archived — add it in the Instruments tab to start collecting it.`;
}

export function createArchiveSource(httpBase: string, wsBase: string): ArchiveSource {
  const http = jsonClient("the candle archive", mapStatus);

  async function readPairs(signal: AbortSignal): Promise<TrackedPair[]> {
    const raw = await http.json<RawTrackedPair[]>(`${httpBase}/pairs`, { signal });
    return raw.map(mapTrackedPair);
  }

  /**
   * Why a subscription that would not open is going to stay shut.
   *
   * The archive refuses a pair nobody chose to collect *before* the handshake,
   * which is the right call — it never hands back a socket that dies a moment
   * later — but it means the refusal is an HTTP status the browser will not
   * show us. What reaches the page is a connection that failed, the same shape
   * as an archive that is down, and the two deserve opposite responses: one is
   * worth retrying, the other is worth telling the operator about.
   *
   * So the question gets asked a second way. `/pairs` is the same list the
   * Archive tab reads, and a pair missing from it is a settled answer: nothing
   * is collecting this, and nothing will until somebody decides otherwise. Any
   * other outcome — the pair is listed, or `/pairs` cannot be reached either —
   * returns `null`, and the hub goes on retrying.
   */
  async function whyRefused(symbol: string, resolution: Resolution): Promise<string | null> {
    // The question gets a deadline. An archive that accepts the request and
    // never answers is an archive worth retrying, and without this the retry
    // loop would wait on it forever instead — the diagnosis would have become
    // the outage.
    const abort = new AbortController();
    const deadline = setTimeout(() => abort.abort(), DIAGNOSIS_TIMEOUT_MS);
    try {
      return readRefusalFromPairs(await readPairs(abort.signal), symbol, resolution);
    } finally {
      clearTimeout(deadline);
    }
  }

  const hub = new SocketHub(
    (symbol, resolution) =>
      `${wsBase}/candles?symbol=${encodeURIComponent(symbol)}&resolution=${resolution}`,
    translateMessage,
    undefined,
    undefined,
    whyRefused,
  );

  return {
    id: "archive",
    label: "market-data",
    whenUnreachable: "the candles on screen are stale",

    async ping(signal) {
      await http.json(`${httpBase}/health`, { signal });
    },

    async history(request: HistoryRequest, signal): Promise<Bar[]> {
      const url =
        `${httpBase}/candles/${encodeURIComponent(request.symbol)}` +
        `?resolution=${request.resolution}` +
        `&from=${encodeURIComponent(toIso(request.from))}` +
        `&to=${encodeURIComponent(toIso(request.to))}`;
      const raw = await http.json<RawCandles>(url, { signal });
      const bars: Bar[] = [];
      for (const candle of raw.candles) {
        // A range read answers with settled candles only; the period still
        // being built reaches a consumer through the subscription.
        const bar = toBar(candle, false);
        if (bar) bars.push(bar);
      }
      return bars;
    },

    subscribe(symbol, resolution, sink) {
      return hub.subscribe(symbol, resolution, sink);
    },

    async listPairs(signal) {
      return readPairs(signal);
    },

    async trackPairs(pairs: PairRequest[], collectFrom, signal) {
      const raw = await http.json<RawTrackPairsResult>(`${httpBase}/pairs`, {
        signal,
        method: "POST",
        body: {
          pairs: pairs.map((pair) => ({ symbol: pair.symbol, resolution: pair.resolution })),
          ...(collectFrom === null ? {} : { collect_from: toIso(collectFrom) }),
        },
      });
      return mapTrackPairsResult(raw);
    },

    async untrackPair(symbol, resolution, signal) {
      // 204, no body to read.
      await http.send(
        `${httpBase}/pairs/${encodeURIComponent(symbol)}?resolution=${resolution}`,
        { signal, method: "DELETE" },
      );
    },

    async coverage(symbol, resolution, signal): Promise<PairCoverage> {
      const url = `${httpBase}/coverage/${encodeURIComponent(symbol)}?resolution=${resolution}`;
      const raw = await http.json<RawCoverage>(url, { signal });
      return {
        symbol: raw.symbol,
        resolution: raw.resolution as Resolution,
        ranges: raw.ranges.map((range) => ({
          from: parseIsoToEpochSeconds(range.from),
          to: parseIsoToEpochSeconds(range.to),
          historyEnded: range.history_ended,
        })),
        earliestReachable:
          raw.earliest_reachable === null ? null : parseIsoToEpochSeconds(raw.earliest_reachable),
      };
    },

    async estimateJob(pairs: PairRequest[], collectFrom, signal): Promise<JobEstimate> {
      const raw = await http.json<RawJobEstimate>(`${httpBase}/jobs/estimate`, {
        signal,
        method: "POST",
        body: {
          pairs: pairs.map((pair) => ({ symbol: pair.symbol, resolution: pair.resolution })),
          collect_from: toIso(collectFrom),
        },
      });
      return mapJobEstimate(raw);
    },

    async listJobs(symbol, resolution, signal): Promise<JobPairView[]> {
      const params = new URLSearchParams();
      if (symbol !== null) params.set("symbol", symbol);
      if (resolution !== null) params.set("resolution", resolution);
      const query = params.toString();
      const raw = await http.json<RawJobPairView[]>(
        `${httpBase}/jobs${query ? `?${query}` : ""}`,
        { signal },
      );
      return raw.map(mapJobPairView);
    },

    async readJob(jobId, signal): Promise<Job> {
      const raw = await http.json<RawJob>(`${httpBase}/jobs/${jobId}`, { signal });
      return mapJob(raw);
    },

    async retryJob(jobId, signal): Promise<Job> {
      const raw = await http.json<RawJob>(`${httpBase}/jobs/${jobId}/retry`, {
        signal,
        method: "POST",
      });
      return mapJob(raw);
    },
  };
}
