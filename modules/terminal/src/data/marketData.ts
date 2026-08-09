import { createArchiveSource } from "./archive";
import { resolveEndpoints } from "./config";
import { createGatewaySource } from "./gatewaySource";
import type { ArchiveAdmin, MarketDataSource } from "./source";

/**
 * The one market-data source the app runs on — and, behind it, the two back
 * ends it is made of.
 *
 * Candles and the live stream come from `market-data`, the archive; the
 * instrument catalogue is `capital-gateway`'s, which owns it. No view knows
 * that: they take `marketData` and call it, and the split is this file's
 * business alone (terminal-market-data spec, "Świece i instrumenty idą
 * z różnych miejsc"). That is also what makes it a rollback rather than a
 * rewrite if the archive ever has to come back out — the seam is here.
 *
 * **Both now go through the same host.** `capital-gateway` is not public, so
 * the browser cannot reach it directly — `gatewaySource` calls `market-data`,
 * which proxies its three catalogue routes to the gateway unread
 * (`gatewaySource.ts` has the detail). The split above is still real — it is
 * still the gateway's data and the gateway's rules — only the wire hop
 * changed, which is exactly the kind of thing this seam exists to absorb
 * without every view needing to know.
 *
 * A single module-level instance, so every view shares one socket hub — that
 * sharing is what makes six charts on the same pair one connection rather than
 * six.
 */
const { archiveHttp, archiveWs } = resolveEndpoints();

const archiveSource = createArchiveSource(archiveHttp, archiveWs);
const gateway = createGatewaySource(archiveHttp);

export const marketData: MarketDataSource = {
  // Ordered the way the shell reads them out, candles first: the archive is the
  // one whose absence empties a chart.
  parts: [archiveSource, gateway],

  history: (request, signal) => archiveSource.history(request, signal),
  subscribe: (symbol, resolution, sink) => archiveSource.subscribe(symbol, resolution, sink),

  searchInstruments: (query, signal, assetClass) =>
    gateway.searchInstruments(query, signal, assetClass),
  listInstruments: (signal, assetClass) => gateway.listInstruments(signal, assetClass),
};

/** The instrument catalogue's own admin surface — asset classes, and a
 *  class-narrowed listing — for the wizard's first two autocomplete steps.
 *  Not part of `MarketDataSource`: no chart or search-as-you-type view has
 *  any use for it. */
export const instruments = gateway;

/**
 * The same archive, seen as the thing the operator administers rather than the
 * thing a chart reads. Narrowed to `ArchiveAdmin` on purpose: the panel manages
 * what is collected, and reading candles through it would go around the one
 * interface every view is supposed to use.
 */
export const archive: ArchiveAdmin = archiveSource;
