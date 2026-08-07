import { hashString, mulberry32 } from "./mockRng";
import { FIXED_RESOLUTION_SECONDS } from "./types";
import type { Bar, Instrument, InstrumentPage, Resolution, StreamEvent } from "./types";
import type { MarketDataSource } from "./source";

/**
 * A source with no network: deterministic synthetic candles, seeded from the
 * symbol (and resolution, so MINUTE and MINUTE_5 on the same symbol don't
 * replay an identical walk) — task 3.6. Every price is a closed-form function
 * of its period index rather than a sequentially-replayed walk, so asking for
 * more history never repaints the bars a shorter request already returned, and
 * a subscription's forming bar picks up exactly where `history()` left off
 * without the two needing to coordinate.
 */

// DAY and WEEK have no real venue session to be faithful to here — the mock
// *is* the source, so unlike the gateway adapter (see design.md) it is free to
// pick its own fixed-length boundary for these two.
const MOCK_PERIOD_SECONDS: Record<Resolution, number> = {
  ...(FIXED_RESOLUTION_SECONDS as Record<Resolution, number>),
  DAY: 86_400,
  WEEK: 604_800,
};

interface SeededParams {
  base: number;
  amp1: number;
  freq1: number;
  phase1: number;
  amp2: number;
  freq2: number;
  phase2: number;
  // A third, slow, wide swing standing in for a "trend" — a literal linear
  // drift term would eventually overflow, since a period index derived from
  // an epoch second (MINUTE resolution) already runs into the tens of
  // millions today. A bounded sine never can, at any index magnitude.
  amp3: number;
  freq3: number;
  phase3: number;
}

function seededParams(seed: string): SeededParams {
  const rng = mulberry32(hashString(seed));
  return {
    base: 20 + rng() * 480,
    amp1: 0.01 + rng() * 0.03,
    freq1: 0.01 + rng() * 0.05,
    phase1: rng() * Math.PI * 2,
    amp2: 0.005 + rng() * 0.015,
    freq2: 0.05 + rng() * 0.2,
    phase2: rng() * Math.PI * 2,
    amp3: 0.05 + rng() * 0.1,
    freq3: 0.000005 + rng() * 0.000045,
    phase3: rng() * Math.PI * 2,
  };
}

const WICK_NOISE = 0.0025;

function smooth(params: SeededParams, x: number): number {
  const wave =
    1 +
    params.amp1 * Math.sin(params.freq1 * x + params.phase1) +
    params.amp2 * Math.sin(params.freq2 * x + params.phase2) +
    params.amp3 * Math.sin(params.freq3 * x + params.phase3);
  return params.base * wave;
}

/** Price at a real-valued position in units of whole periods. The smooth trend
 *  is continuous in `position`; the noise term is quantized to quarter-period
 *  steps so it stays constant within a quarter and — critically — so a bar's
 *  closing sample and the next bar's opening sample land on the same absolute
 *  quarter and agree exactly, keeping the series gap-free at every boundary. */
function priceAt(seed: string, params: SeededParams, position: number): number {
  const quarterKey = Math.floor(position * 4);
  const noise = mulberry32(hashString(`${seed}:noise:${quarterKey}`))() * 2 - 1;
  return Math.max(0.01, smooth(params, position) * (1 + noise * WICK_NOISE));
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

function volumeAt(seed: string, index: number): number {
  return Math.round(100 + mulberry32(hashString(`${seed}:vol:${index}`))() * 900);
}

/** One fully settled bar at a whole period index — what `history()` returns,
 *  and what a live subscription emits once a period closes behind it. */
function settledBarAt(seed: string, params: SeededParams, period: number, index: number): Bar {
  const time = index * period;
  const open = priceAt(seed, params, index);
  const close = priceAt(seed, params, index + 1);
  const samples = [open, priceAt(seed, params, index + 0.25), priceAt(seed, params, index + 0.5), priceAt(seed, params, index + 0.75), close];
  return {
    time,
    open: round2(open),
    high: round2(Math.max(...samples)),
    low: round2(Math.min(...samples)),
    close: round2(close),
    volume: volumeAt(seed, index),
    forming: false,
  };
}

/** The still-open bar at `nowSeconds`, built from however much of its period
 *  has elapsed. Volume is null, matching the gateway's own streamed candles —
 *  see terminal-market-data spec. */
function formingBarAt(
  seed: string,
  params: SeededParams,
  period: number,
  index: number,
  nowSeconds: number,
): Bar {
  const time = index * period;
  const progress = (nowSeconds - time) / period;
  const open = priceAt(seed, params, index);
  const samples = [open];
  for (const f of [0.25, 0.5, 0.75, 1]) {
    if (f <= progress) samples.push(priceAt(seed, params, index + f));
  }
  const current = priceAt(seed, params, index + progress);
  samples.push(current);
  return {
    time,
    open: round2(open),
    high: round2(Math.max(...samples)),
    low: round2(Math.min(...samples)),
    close: round2(current),
    volume: null,
    forming: true,
  };
}

export function generateHistory(
  symbol: string,
  resolution: Resolution,
  count: number,
  nowSeconds: number,
): Bar[] {
  const period = MOCK_PERIOD_SECONDS[resolution];
  const seed = `${symbol}:${resolution}`;
  const params = seededParams(seed);
  const nowIndex = Math.floor(nowSeconds / period);
  const lastSettled = nowIndex - 1;
  const start = lastSettled - count + 1;
  const bars: Bar[] = [];
  for (let index = start; index <= lastSettled; index++) {
    bars.push(settledBarAt(seed, params, period, index));
  }
  return bars;
}

const CATALOG: ReadonlyArray<Omit<Instrument, "bid" | "ask">> = [
  { symbol: "US100", name: "US Tech 100", assetClass: "INDICES", tradeable: true },
  { symbol: "US500", name: "US 500", assetClass: "INDICES", tradeable: true },
  { symbol: "UK100", name: "FTSE 100", assetClass: "INDICES", tradeable: true },
  { symbol: "GER40", name: "Germany 40", assetClass: "INDICES", tradeable: true },
  { symbol: "GOLD", name: "Gold", assetClass: "COMMODITIES", tradeable: true },
  { symbol: "SILVER", name: "Silver", assetClass: "COMMODITIES", tradeable: true },
  { symbol: "OIL_CRUDE", name: "Crude Oil", assetClass: "COMMODITIES", tradeable: true },
  { symbol: "BTCUSD", name: "Bitcoin", assetClass: "CRYPTO", tradeable: true },
  { symbol: "ETHUSD", name: "Ethereum", assetClass: "CRYPTO", tradeable: true },
  { symbol: "EURUSD", name: "Euro / US Dollar", assetClass: "CURRENCIES", tradeable: true },
  { symbol: "GBPUSD", name: "British Pound / US Dollar", assetClass: "CURRENCIES", tradeable: true },
  { symbol: "USDJPY", name: "US Dollar / Japanese Yen", assetClass: "CURRENCIES", tradeable: true },
  { symbol: "AAPL", name: "Apple", assetClass: "SHARES", tradeable: true },
  { symbol: "TSLA", name: "Tesla", assetClass: "SHARES", tradeable: true },
  { symbol: "MSFT", name: "Microsoft", assetClass: "SHARES", tradeable: true },
];

function quoteFor(symbol: string, nowSeconds: number): { bid: number; ask: number } {
  const params = seededParams(`${symbol}:MINUTE`);
  const price = priceAt(`${symbol}:MINUTE`, params, nowSeconds / MOCK_PERIOD_SECONDS.MINUTE);
  const spread = Math.max(0.01, price * 0.0006);
  return { bid: round2(price - spread / 2), ask: round2(price + spread / 2) };
}

interface MockEntry {
  sinks: Set<(event: StreamEvent) => void>;
  seed: string;
  params: SeededParams;
  period: number;
  lastIndex: number | null;
  timer: ReturnType<typeof setInterval> | null;
}

const TICK_MS = 1000;

export function createMockSource(now: () => number = Date.now): MarketDataSource {
  const entries = new Map<string, MockEntry>();

  function broadcast(entry: MockEntry, event: StreamEvent): void {
    for (const sink of entry.sinks) sink(event);
  }

  function tick(entry: MockEntry): void {
    const nowSeconds = Math.floor(now() / 1000);
    const index = Math.floor(nowSeconds / entry.period);
    if (entry.lastIndex !== null && index > entry.lastIndex) {
      broadcast(entry, {
        kind: "bar",
        bar: settledBarAt(entry.seed, entry.params, entry.period, entry.lastIndex),
      });
    }
    entry.lastIndex = index;
    const bar = formingBarAt(entry.seed, entry.params, entry.period, index, nowSeconds);
    broadcast(entry, { kind: "bar", bar });
    const spread = Math.max(0.01, bar.close * 0.0006);
    broadcast(entry, {
      kind: "quote",
      time: now(),
      bid: round2(bar.close - spread / 2),
      ask: round2(bar.close + spread / 2),
    });
  }

  return {
    id: "mock",

    async searchInstruments(query) {
      const nowSeconds = Math.floor(now() / 1000);
      const needle = query.trim().toLowerCase();
      return CATALOG.filter(
        (i) => i.symbol.toLowerCase().includes(needle) || i.name.toLowerCase().includes(needle),
      ).map((i) => ({ ...i, ...quoteFor(i.symbol, nowSeconds) }));
    },

    async listInstruments() {
      const nowSeconds = Math.floor(now() / 1000);
      const instruments: Instrument[] = CATALOG.map((i) => ({
        ...i,
        ...quoteFor(i.symbol, nowSeconds),
      }));
      const page: InstrumentPage = { instruments, count: instruments.length, truncated: false };
      return page;
    },

    async history(request) {
      return generateHistory(request.symbol, request.resolution, request.count, Math.floor(now() / 1000));
    },

    subscribe(symbol, resolution, sink) {
      const key = `${symbol}|${resolution}`;
      let entry = entries.get(key);
      if (!entry) {
        const seed = `${symbol}:${resolution}`;
        const period = MOCK_PERIOD_SECONDS[resolution];
        entry = {
          sinks: new Set(),
          seed,
          params: seededParams(seed),
          period,
          lastIndex: null,
          timer: null,
        };
        entries.set(key, entry);
        entry.timer = setInterval(() => tick(entry!), TICK_MS);
      }
      entry.sinks.add(sink);
      sink({ kind: "status", state: "connected" });
      const nowSeconds = Math.floor(now() / 1000);
      const index = Math.floor(nowSeconds / entry.period);
      entry.lastIndex ??= index;
      sink({
        kind: "bar",
        bar: formingBarAt(entry.seed, entry.params, entry.period, index, nowSeconds),
      });

      return () => {
        const current = entries.get(key);
        if (!current) return;
        current.sinks.delete(sink);
        if (current.sinks.size === 0) {
          if (current.timer !== null) clearInterval(current.timer);
          entries.delete(key);
        }
      };
    },
  };
}
