import { createEntraIdentities } from "../auth/entra";
import { noIdentity, type Identity } from "../auth/identity";
import { createArchiveSource } from "./archive";
import { resolveEndpoints, resolveEntra } from "./config";
import { createGatewaySource } from "./gatewaySource";
import type { ArchiveAdmin, IndicatorSource, MarketDataSource } from "./source";

/**
 * Candles from the archive, the instrument catalogue from `capital-gateway`, which owns it and is not public, so
 * the calls go through market-data unread. Keeping the seam here makes the archive a rollback, not a rewrite.
 */
const { archiveHttp, archiveWs } = resolveEndpoints();


/**
 * The operator's identity, or the absence of one, wired here for the reason the back ends are: a view consuming
 * it directly would be a view that knew about Entra. `null` is a working mode, not a failure.
 */
const entraConfig = resolveEntra();
const identities = entraConfig === null ? null : createEntraIdentities(entraConfig);

/** Resolves the redirect the operator is arriving back from, before the app mounts. A
 *  no-op with no identity configured. Exported rather than reached for by a cast on
 *  `identity`, which is what it used to be — a cast that would now silently find nothing
 *  and skip MSAL's own initialization. */
export const initializeIdentity = (): Promise<void> =>
  identities?.initialize() ?? Promise.resolve();

function scopeFor(pick: (s: NonNullable<typeof entraConfig>["scopes"]) => string | null) {
  return entraConfig === null ? noIdentity : (identities?.for(pick(entraConfig.scopes)) ?? noIdentity);
}

/**
 * One identity per module rather than one for the terminal: each back end accepts a token minted for its own
 * audience. A module whose scope is unset gets `noIdentity` — bare calls, refused by its own gate, nameably.
 */
export const identity: Identity = identities?.shared ?? noIdentity;

/** The workbench — the conversation and the teams catalogue, one process and one
 *  audience. */
export const workbenchIdentity: Identity = scopeFor((s) => s.workbench);

/** `capital-gateway`, for the Accounts screen, which calls it on its own hostname. Not
 *  for `gatewaySource` below: that one reaches the catalogue *through* the archive, so it
 *  is an archive call and carries the archive's token. */
export const gatewayIdentity: Identity = scopeFor((s) => s.gateway);

/** `polymarket-data`, for the prediction-market tab. */
export const polymarketIdentity: Identity = scopeFor((s) => s.polymarket);

/** `strategy`, for the strategy tab. */
export const strategyIdentity: Identity = scopeFor((s) => s.strategy);

/** `social-data`, for the posts tab. */
export const socialIdentity: Identity = scopeFor((s) => s.social);

const archiveSource = createArchiveSource(archiveHttp, archiveWs, identity);
const gateway = createGatewaySource(archiveHttp, identity);

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
 * The same archive, seen as the thing the operator administers. Narrowed to `ArchiveAdmin` on purpose: reading
 * candles through it would go around the one interface every view is supposed to use.
 */
export const archive: ArchiveAdmin = archiveSource;

/** The same archive again, narrowed to the indicators it can compute — only the chart
 *  and its picker have any business with this. */
export const indicators: IndicatorSource = archiveSource;
