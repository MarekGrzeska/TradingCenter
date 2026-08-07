import { jsonClient } from "./http";
import { SocketHub } from "./socketHub";
import { parseIsoToEpochSeconds } from "./time";
import { MarketDataError } from "./types";
import type {
  Bar,
  CollectionState,
  PairCoverage,
  Resolution,
  StreamEvent,
  TrackedPair,
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
  latest_candle: string | null;
  collection: string;
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
    latestCandle: raw.latest_candle === null ? null : parseIsoToEpochSeconds(raw.latest_candle),
    collection: raw.collection as CollectionState,
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

export function createArchiveSource(httpBase: string, wsBase: string): ArchiveSource {
  const http = jsonClient("the candle archive", mapStatus);

  const hub = new SocketHub(
    (symbol, resolution) =>
      `${wsBase}/candles?symbol=${encodeURIComponent(symbol)}&resolution=${resolution}`,
    translateMessage,
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
      const raw = await http.json<RawTrackedPair[]>(`${httpBase}/pairs`, { signal });
      return raw.map(mapTrackedPair);
    },

    async trackPair(symbol, resolution, signal) {
      const raw = await http.json<RawTrackedPair>(`${httpBase}/pairs`, {
        signal,
        method: "POST",
        body: { symbol, resolution },
      });
      return mapTrackedPair(raw);
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
  };
}
