import { noIdentity, type Identity } from "../auth/identity";
import type { components } from "./contract.generated";
import { jsonClient } from "./http";
import { SocketHub } from "./socketHub";
import { parseIsoToEpochSeconds } from "./time";
import { MarketDataError } from "./types";
import type {
  Bar,
  Chunk,
  ChunkState,
  CollectionState,
  IndicatorCatalogue,
  IndicatorCatalogueEntry,
  IndicatorLevel,
  IndicatorMarker,
  IndicatorResult,
  IndicatorSelection,
  IndicatorsResult,
  IndicatorZone,
  Job,
  JobEstimate,
  JobPairView,
  JobStatus,
  PairCoverage,
  PairDeletion,
  PairEstimate,
  PairRequest,
  Resolution,
  StreamEvent,
  TrackedPair,
  TrackedPairResult,
  TrackPairsResult,
} from "./types";
import type { ArchiveAdmin, CandleSource, HistoryRequest, IndicatorSource } from "./source";

/**
 * The candle side of the terminal's source: `market-data`, over its HTTP contract and
 * its subscription.
 *
 * The subscription is why this module has the shape it does. Its first message is the
 * series itself, read while the archive holds its room still, so there is nothing to
 * splice, nothing to fetch after a reconnect and no duplicate to filter (design.md,
 * "Archiwum jest dla terminala jedynym źródłem świec i strumienia").
 *
 * `market-data`'s wire shapes (snake_case, per its OpenAPI schema) are private to this
 * file. Nothing outside it ever sees one.
 */

/**
 * The wire shapes, taken from market-data's own OpenAPI document rather than described
 * again here — thirteen hand-written interfaces were thirteen chances to disagree with
 * the server silently, a renamed field arriving as `undefined` and showing up as a blank
 * cell. Now a rename stops this file compiling, on the line that reads the field.
 *
 * Regenerate with `pnpm contract:generate` after changing a model in `contract.py`;
 * `pnpm contract:check` fails when the committed file is stale.
 */
type Wire = components["schemas"];

type RawCandle = Wire["CandleOut"];
type RawCandles = Wire["CandlesOut"];
/** The subscription's candle, which is the archive's own storage shape rather than the
 *  one the range endpoint answers with. It has no HTTP path, so market-data publishes it
 *  as a component on purpose (`openapi.py`). */
type RawStreamCandle = Wire["Candle"];
type RawCoverage = Wire["PairCoverageOut"];
type RawTrackedPair = Wire["TrackedPairOut"];
type RawChunk = Wire["ChunkOut"];
type RawJobPairView = Wire["JobPairViewOut"];
type RawJob = Wire["JobOut"];
type RawPairEstimate = Wire["PairEstimateOut"];
type RawJobEstimate = Wire["JobEstimateOut"];
// No alias for `TrackedPairResult`: it was only ever named so the interface above could
// refer to it, and that relationship now lives in the generated types.
type RawTrackPairsResult = Wire["TrackPairsResult"];
type RawPairDeletion = Wire["PairDeletionOut"];
type RawStreamTicket = Wire["StreamTicketOut"];
type RawIndicatorCatalogueEntry = Wire["IndicatorCatalogueEntryOut"];
type RawIndicatorsCatalogue = Wire["IndicatorsCatalogueOut"];
type RawIndicatorResult = Wire["IndicatorResultOut"];
type RawIndicatorsOut = Wire["IndicatorsOut"];

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
    candleCount: raw.candle_count,
    estimatedBytes: raw.estimated_bytes,
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
    lastActivityAt: parseIsoToEpochSeconds(raw.last_activity_at),
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
    lastActivityAt: parseIsoToEpochSeconds(raw.last_activity_at),
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

function mapPairDeletion(raw: RawPairDeletion): PairDeletion {
  return {
    symbol: raw.symbol,
    resolution: raw.resolution as Resolution,
    deletedAt: parseIsoToEpochSeconds(raw.deleted_at),
    candlesRemoved: raw.candles_removed,
    removedFrom: raw.removed_from === null ? null : parseIsoToEpochSeconds(raw.removed_from),
    removedTo: raw.removed_to === null ? null : parseIsoToEpochSeconds(raw.removed_to),
  };
}

function mapIndicatorCatalogueEntry(raw: RawIndicatorCatalogueEntry): IndicatorCatalogueEntry {
  return {
    id: raw.id,
    name: raw.name,
    aliases: raw.aliases,
    group: raw.group,
    output: raw.output,
    params: raw.params,
    lines: raw.lines,
    render: {
      pane: raw.render.pane,
      style: raw.render.style,
      scale: raw.render.scale,
      autoscale: raw.render.autoscale,
      range: raw.render.range,
      levels: raw.render.levels,
    },
    warmupKind: raw.warmup_kind,
  };
}

function mapIndicatorCatalogue(raw: RawIndicatorsCatalogue): IndicatorCatalogue {
  return {
    algorithmVersion: raw.algorithm_version,
    indicators: raw.indicators.map(mapIndicatorCatalogueEntry),
  };
}

function mapIndicatorResult(raw: RawIndicatorResult): IndicatorResult {
  return {
    id: raw.id,
    params: raw.params,
    warmupBars: raw.warmup_bars,
    anchoredAt: raw.anchored_at === null ? null : parseIsoToEpochSeconds(raw.anchored_at),
    settled: raw.settled,
    lines: raw.lines,
    markers:
      raw.markers === null
        ? null
        : raw.markers.map(
            (marker): IndicatorMarker => ({
              time: parseIsoToEpochSeconds(marker.time),
              label: marker.label,
              price: marker.price,
            }),
          ),
    zones:
      raw.zones === null
        ? null
        : raw.zones.map(
            (zone): IndicatorZone => ({
              from: parseIsoToEpochSeconds(zone.from),
              to: zone.to === null ? null : parseIsoToEpochSeconds(zone.to),
              top: zone.top,
              bottom: zone.bottom,
              direction: zone.direction,
              touchedAt: zone.touched_at === null ? null : parseIsoToEpochSeconds(zone.touched_at),
              filledAt: zone.filled_at === null ? null : parseIsoToEpochSeconds(zone.filled_at),
            }),
          ),
    levels:
      raw.levels === null
        ? null
        : raw.levels.map(
            (level): IndicatorLevel => ({
              from: parseIsoToEpochSeconds(level.from),
              price: level.price,
              label: level.label,
              count: level.count,
            }),
          ),
  };
}

function mapIndicatorsResult(raw: RawIndicatorsOut): IndicatorsResult {
  return {
    symbol: raw.symbol,
    resolution: raw.resolution as Resolution,
    derived: raw.derived,
    algorithmVersion: raw.algorithm_version,
    times: raw.times.map(parseIsoToEpochSeconds),
    results: raw.results.map(mapIndicatorResult),
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

export type ArchiveSource = CandleSource & ArchiveAdmin & IndicatorSource;

/** How long the "why did that socket not open" question may take before the
 *  answer stops being worth waiting for. Short, because a chart is sitting on
 *  it and the fallback — keep retrying — is the safe one. */
const DIAGNOSIS_TIMEOUT_MS = 5_000;

/** How long asking for a stream ticket may take before the attempt counts as
 *  failed. Shorter than the diagnosis above: nothing is on screen waiting for
 *  it yet, and the socket it precedes cannot open until it answers. */
const TICKET_TIMEOUT_MS = 5_000;

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

export function createArchiveSource(
  httpBase: string,
  wsBase: string,
  identity: Identity = noIdentity,
): ArchiveSource {
  const http = jsonClient("the candle archive", mapStatus, identity);

  async function readPairs(signal: AbortSignal): Promise<TrackedPair[]> {
    const raw = await http.json<RawTrackedPair[]>(`${httpBase}/pairs`, { signal });
    return raw.map(mapTrackedPair);
  }

  /**
   * Why a subscription that would not open is going to stay shut.
   *
   * The archive refuses an uncollected pair before the handshake, so the refusal is an
   * HTTP status the browser will not show — what reaches the page looks exactly like an
   * archive that is down, and the two deserve opposite responses. So the question is
   * asked a second way: a pair missing from `/pairs` is a settled answer. Anything else,
   * including `/pairs` being unreachable, returns `null` and the hub goes on retrying.
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

  /**
   * Where one pair's stream lives — not a constant, because opening it costs a ticket.
   *
   * A browser cannot put a header on a WebSocket handshake, so the token cannot reach
   * it. The archive's answer is a one-time ticket, asked for here over HTTP where the
   * header works normally. The token itself never goes near the address: addresses end
   * up in server logs, and a token stays good for the better part of an hour.
   *
   * One ticket per attempt, never cached — a spent ticket is refused, and a reconnect
   * reusing the last one would fail every time and look like an archive that had gone.
   */
  async function streamUrl(symbol: string, resolution: Resolution): Promise<string> {
    // No caller-supplied signal: this runs inside the hub's reconnect loop,
    // which has no request to attach to. The deadline is its own, and its
    // failure is a failed attempt like any other — the hub retries it.
    const abort = new AbortController();
    const deadline = setTimeout(() => abort.abort(), TICKET_TIMEOUT_MS);
    let ticket: string;
    try {
      const issued = await http.json<RawStreamTicket>(`${httpBase}/stream-tickets`, {
        method: "POST",
        signal: abort.signal,
      });
      ticket = issued.ticket;
    } finally {
      clearTimeout(deadline);
    }
    return (
      `${wsBase}/candles?symbol=${encodeURIComponent(symbol)}` +
      `&resolution=${resolution}&ticket=${encodeURIComponent(ticket)}`
    );
  }

  const hub = new SocketHub(streamUrl, translateMessage, undefined, undefined, whyRefused);

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

    async deletePair(symbol, resolution, signal): Promise<PairDeletion> {
      const raw = await http.json<RawPairDeletion>(
        `${httpBase}/pairs/${encodeURIComponent(symbol)}?resolution=${resolution}`,
        { signal, method: "DELETE" },
      );
      return mapPairDeletion(raw);
    },

    async listDeletions(symbol, resolution, signal): Promise<PairDeletion[]> {
      const params = new URLSearchParams();
      if (symbol !== null) params.set("symbol", symbol);
      if (resolution !== null) params.set("resolution", resolution);
      const query = params.toString();
      const raw = await http.json<RawPairDeletion[]>(
        `${httpBase}/deletions${query ? `?${query}` : ""}`,
        { signal },
      );
      return raw.map(mapPairDeletion);
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

    async deleteJob(jobId, signal): Promise<void> {
      // 204, so `send` rather than `json` — there is no body, and asking for one
      // would fail on the success path.
      await http.send(`${httpBase}/jobs/${jobId}`, { signal, method: "DELETE" });
    },

    async indicatorCatalogue(signal): Promise<IndicatorCatalogue> {
      const raw = await http.json<RawIndicatorsCatalogue>(`${httpBase}/indicators`, { signal });
      return mapIndicatorCatalogue(raw);
    },

    async computeIndicators(
      symbol: string,
      resolution: Resolution,
      from: number,
      to: number,
      specs: IndicatorSelection[],
      signal: AbortSignal,
    ): Promise<IndicatorsResult> {
      const raw = await http.json<RawIndicatorsOut>(
        `${httpBase}/indicators/${encodeURIComponent(symbol)}`,
        {
          signal,
          method: "POST",
          body: {
            resolution,
            from: toIso(from),
            to: toIso(to),
            specs: specs.map((spec) => ({ id: spec.id, params: spec.params })),
          },
        },
      );
      return mapIndicatorsResult(raw);
    },
  };
}
