import { createEntraIdentities } from "../auth/entra";
import { noIdentity, type Identity } from "../auth/identity";
import { createArchiveSource } from "./archive";
import { resolveEndpoints, resolveEntra } from "./config";
import { createGatewaySource } from "./gatewaySource";
import type { ArchiveAdmin, IndicatorSource, MarketDataSource } from "./source";

/**
 * The one market-data source the app runs on, and the two back ends behind it.
 *
 * Candles and the live stream come from the archive; the instrument catalogue is
 * `capital-gateway`'s, which owns it. No view knows that (terminal-market-data spec,
 * "Świece i instrumenty idą z różnych miejsc"), and keeping the seam here is what makes
 * the archive a rollback rather than a rewrite if it ever has to come back out.
 *
 * Both reach the same host: `capital-gateway` is not public, so `gatewaySource` calls
 * `market-data`, which proxies the three catalogue routes to it unread. Whose data and
 * whose rules is unchanged — only the wire hop, which is what this seam absorbs.
 *
 * A single module-level instance, so six charts on one pair share one socket rather
 * than opening six.
 */
const { archiveHttp, archiveWs } = resolveEndpoints();


/**
 * The operator's identity, or the absence of one. A wiring decision, made here for the
 * same reason the back ends are composed here: a view that consumed it directly would be
 * a view that had to know about Entra. `null` configuration is a working mode — local
 * development, nothing in front of the archive — and answers "no credential" rather than
 * failing.
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
 * The shared sign-in state, and the credential for the archive.
 *
 * One per module rather than one for the terminal: each back end accepts a token minted
 * for its own audience, so a token taken for one is not sent to another
 * (terminal-identity, "Każde wywołanie archiwum niesie poświadczenie"). They share the
 * account and the state — `TopBar` subscribing to this one sees every change — and differ
 * only in what they ask Entra for. A module whose scope is unset gets `noIdentity`: its
 * calls go out bare and its own gate refuses them, which is a refusal a tab can name.
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
 * The same archive, seen as the thing the operator administers rather than the
 * thing a chart reads. Narrowed to `ArchiveAdmin` on purpose: the panel manages
 * what is collected, and reading candles through it would go around the one
 * interface every view is supposed to use.
 */
export const archive: ArchiveAdmin = archiveSource;

/** The same archive again, narrowed to the indicators it can compute — only the chart
 *  and its picker have any business with this. */
export const indicators: IndicatorSource = archiveSource;
