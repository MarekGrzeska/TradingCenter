import { noIdentity, type Identity } from "../auth/identity";
import { jsonClient } from "./http";
import { MarketDataError } from "./types";
import type { AssetClass, Instrument, InstrumentPage } from "./types";
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
 * **The wire path changed, the ownership did not.** `capital-gateway` is not
 * public — the terminal cannot reach it from the browser — so this now calls
 * `market-data`, which proxies these three routes to the gateway unmodified
 * (openspec/changes/provision-azure-platform, design.md, "Terminal osiąga
 * katalog instrumentów przez market-data"). The paths and shapes below are
 * still the gateway's own; only the host this source is constructed with
 * changed, in `marketData.ts`. The practical consequence stated in the
 * original design no longer holds exactly as written: a `market-data` outage
 * now takes the search with it too, since both go through the same process.
 * What still holds is that a *gateway* refusal (capital.com trouble, a bad
 * caller key) is distinguishable from an archive outage — `market-data`
 * answers those with a `502`, not a silently empty result.
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

export function createGatewaySource(
  httpBase: string,
  identity: Identity = noIdentity,
): InstrumentSource {
  // The same identity the archive uses, because this is the same deployment: the
  // catalogue is the gateway's data, but the address answering for it is
  // market-data's, behind the same authenticator.
  const http = jsonClient("capital-gateway", mapStatus, identity);

  return {
    id: "gateway",
    label: "capital-gateway",
    whenUnreachable: "instrument search is unavailable",

    async searchInstruments(query, signal, assetClass) {
      // The gateway's search has no class filter of its own — narrowed here so
      // the wizard's second autocomplete never offers an instrument outside
      // the class already chosen in its first step.
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
      // Not /capabilities: that route is capital-gateway's own and this source
      // no longer reaches it directly. /asset-classes is the cheapest route
      // market-data proxies, and answering it proves the whole path this
      // source actually depends on — market-data up, reachable, and itself
      // able to reach the gateway — not just that market-data is up.
      await http.json(`${httpBase}/asset-classes`, { signal });
    },
  };
}
