import { noIdentity, type Identity } from "../auth/identity";
import { jsonClient, statusMapper } from "./http";
import type { AssetClass, Instrument, InstrumentPage } from "./types";
import type { InstrumentSource } from "./source";

/**
 * The catalogue is `capital-gateway`'s and stays there; only the wire path changed, since the gateway is not
 * reachable from a browser. So an archive outage takes the search with it — a *gateway* refusal answers 502.
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

const mapStatus = statusMapper({ 404: "not-found", 422: "unsupported-resolution" });

export function createGatewaySource(
  httpBase: string,
  identity: Identity = noIdentity,
): InstrumentSource {
  // The same identity the archive uses, because this is the same deployment: the catalogue is the gateway's
  // data, but the address answering for it is market-data's, behind the same authenticator.
  const http = jsonClient("capital-gateway", mapStatus, identity);

  return {
    id: "gateway",
    label: "capital-gateway",
    whenUnreachable: "instrument search is unavailable",

    async searchInstruments(query, signal, assetClass) {
      // The gateway's search has no class filter of its own — narrowed here so the wizard's second
      // autocomplete never offers an instrument outside the class chosen in its first step.
      const url = `${httpBase}/instruments/search?q=${encodeURIComponent(query)}`;
      const raw = await http.json<RawInstrument[]>(url, { signal });
      const instruments = raw.map(mapInstrument);
      return assetClass ? instruments.filter((i) => i.assetClass === assetClass) : instruments;
    },

    async listInstruments(signal, assetClass) {
      const url = `${httpBase}/instruments` + (assetClass ? `?asset_class=${assetClass}` : "");
      const raw = await http.json<RawInstrumentPage>(url, { signal });
      return mapInstrumentPage(raw);
    },

    async listAssetClasses(signal) {
      return await http.json<AssetClass[]>(`${httpBase}/asset-classes`, { signal });
    },

    async ping(signal) {
      // Not /capabilities, which is the gateway's own route: /asset-classes is the cheapest one market-data
      // proxies, and answering it proves the whole path — market-data up *and* able to reach the gateway.
      await http.json(`${httpBase}/asset-classes`, { signal });
    },
  };
}
