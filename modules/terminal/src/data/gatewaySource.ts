import { jsonClient } from "./http";
import { MarketDataError } from "./types";
import type { Instrument, InstrumentPage } from "./types";
import type { InstrumentSource } from "./source";

/**
 * The instrument catalogue, which is `capital-gateway`'s and stays there.
 *
 * This used to serve candles too. It no longer does: the archive keeps them,
 * and it keeps yesterday's as well as today's, which a window onto the provider
 * by definition cannot. What the gateway owns and the archive does not is the
 * catalogue — and trading after it — so that is what remains here (design.md,
 * "Archiwum nie udaje właściciela rzeczy, których nie posiada").
 *
 * The practical consequence is worth stating: the search keeps working while
 * the archive is down, because it never went there.
 *
 * capital-gateway's wire shapes (snake_case, per its OpenAPI schema) are kept
 * private to this file.
 */

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

function mapStatus(status: number, detail: string): MarketDataError {
  if (status === 404) return new MarketDataError("not-found", detail);
  if (status === 422) return new MarketDataError("unsupported-resolution", detail);
  return new MarketDataError("unknown", detail);
}

export function createGatewaySource(httpBase: string): InstrumentSource {
  const http = jsonClient("capital-gateway", mapStatus);

  return {
    id: "gateway",
    label: "capital-gateway",
    whenUnreachable: "instrument search is unavailable",

    async searchInstruments(query, signal) {
      const url = `${httpBase}/instruments/search?q=${encodeURIComponent(query)}`;
      const raw = await http.json<RawInstrument[]>(url, { signal });
      return raw.map(mapInstrument);
    },

    async listInstruments(signal) {
      const raw = await http.json<RawInstrumentPage>(`${httpBase}/instruments`, { signal });
      return mapInstrumentPage(raw);
    },

    async ping(signal) {
      await http.json(`${httpBase}/capabilities`, { signal });
    },
  };
}
