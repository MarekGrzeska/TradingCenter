import { parseIsoToEpochSeconds } from "./time";
import { SocketHub } from "./socketHub";
import { MarketDataError } from "./types";
import type { Bar, Instrument, InstrumentPage, Resolution } from "./types";
import type { HistoryRequest, MarketDataSource } from "./source";

// capital-gateway's wire shapes (snake_case, per its OpenAPI schema) — kept
// private to this file. Nothing outside `gatewaySource.ts` ever sees them; see
// design.md, "`MarketDataSource` — jeden interfejs, trzy przyszłe implementacje".
interface RawInstrument {
  symbol: string;
  name: string;
  asset_class: string;
  tradeable: boolean;
  bid: number | null;
  ask: number | null;
}

interface RawInstrumentPage {
  instruments: RawInstrument[];
  count: number;
  truncated: boolean;
}

interface RawCandle {
  ts: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
}

interface RawCandleHistory {
  candles: RawCandle[];
}

function mapInstrument(raw: RawInstrument): Instrument {
  return {
    symbol: raw.symbol,
    name: raw.name,
    assetClass: raw.asset_class as Instrument["assetClass"],
    tradeable: raw.tradeable,
    bid: raw.bid,
    ask: raw.ask,
  };
}

function mapInstrumentPage(raw: RawInstrumentPage): InstrumentPage {
  return {
    instruments: raw.instruments.map(mapInstrument),
    count: raw.count,
    truncated: raw.truncated,
  };
}

/** A candle missing any OHLC field (the provider reports this for a period with
 *  no trade) can't become a `Bar` — `Bar`'s fields are non-nullable by design, so
 *  such a candle is dropped rather than faked with a zero. */
function mapCandle(raw: RawCandle): Bar | null {
  if (raw.open === null || raw.high === null || raw.low === null || raw.close === null) {
    return null;
  }
  return {
    time: parseIsoToEpochSeconds(raw.ts),
    open: raw.open,
    high: raw.high,
    low: raw.low,
    close: raw.close,
    volume: raw.volume,
    forming: false,
  };
}

async function parseErrorDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") {
      return body.detail;
    }
    // FastAPI's own validation-error shape (a 422 from a bad query param) is a
    // list of {loc, msg, type} objects, not GatewayError's plain string.
    if (Array.isArray(body.detail)) {
      return body.detail
        .map((entry) => (entry && typeof entry === "object" && "msg" in entry ? entry.msg : entry))
        .join("; ");
    }
  } catch {
    // Not JSON, or no body — fall through to the status line below.
  }
  return response.statusText || `HTTP ${response.status}`;
}

async function toMarketDataError(response: Response): Promise<MarketDataError> {
  const detail = await parseErrorDetail(response);
  if (response.status === 404) {
    return new MarketDataError("not-found", detail);
  }
  if (response.status === 422) {
    return new MarketDataError("unsupported-resolution", detail);
  }
  return new MarketDataError("unknown", detail);
}

async function fetchJson<T>(url: string, signal: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, { signal });
  } catch (cause) {
    if (signal.aborted) {
      throw cause;
    }
    throw new MarketDataError("unreachable", "capital-gateway is not reachable");
  }
  if (!response.ok) {
    throw await toMarketDataError(response);
  }
  return (await response.json()) as T;
}

export function createGatewaySource(httpBase: string, wsBase: string): MarketDataSource {
  // The hub owns the signal: it aborts a backfill still in flight when the last
  // subscriber to the pair leaves.
  const fetchRecent = async (
    symbol: string,
    resolution: Resolution,
    count: number,
    signal: AbortSignal,
  ) => history({ symbol, resolution, count }, signal);

  const hub = new SocketHub(wsBase, fetchRecent);

  async function history(request: HistoryRequest, signal: AbortSignal): Promise<Bar[]> {
    const url =
      `${httpBase}/instruments/${encodeURIComponent(request.symbol)}/history` +
      `?resolution=${request.resolution}&bars=${request.count}`;
    const raw = await fetchJson<RawCandleHistory>(url, signal);
    const bars: Bar[] = [];
    for (const candle of raw.candles) {
      const bar = mapCandle(candle);
      if (bar) bars.push(bar);
    }
    return bars;
  }

  return {
    id: "gateway",

    async searchInstruments(query, signal) {
      const url = `${httpBase}/instruments/search?q=${encodeURIComponent(query)}`;
      const raw = await fetchJson<RawInstrument[]>(url, signal);
      return raw.map(mapInstrument);
    },

    async listInstruments(signal) {
      const raw = await fetchJson<RawInstrumentPage>(`${httpBase}/instruments`, signal);
      return mapInstrumentPage(raw);
    },

    history,

    async ping(signal) {
      await fetchJson(`${httpBase}/capabilities`, signal);
    },

    subscribe(symbol, resolution, sink) {
      return hub.subscribe(symbol, resolution, sink);
    },
  };
}
