/**
 * Where the archive lives — the one back end the terminal holds an address for —
 * accepting a relative path or a full URL.
 *
 * HTTP and WebSocket are configured separately because Static Web Apps cannot proxy the
 * socket (design.md, "Azure Static Web Apps poda statyki, ale nie przeprowadzi
 * strumienia"), so the two may need different hosts. `capital-gateway` has no address
 * here at all: it is not reachable from a browser, and its catalogue arrives proxied
 * through the archive.
 */

const ABSOLUTE_URL = /^https?:\/\//i;
const ABSOLUTE_WS_URL = /^wss?:\/\//i;

/** A relative HTTP path needs no expansion — `fetch("/api/x")` already
 *  resolves against the page origin. Only trims a trailing slash so callers can
 *  join paths with a plain template string. */
export function resolveHttpBase(raw: string): string {
  return raw.replace(/\/+$/, "");
}

/** A relative WS path has no such native resolution — `new WebSocket("/ws")`
 *  throws, because a WebSocket URL must be absolute. This expands it against
 *  the page's own origin, upgrading the scheme (`http`→`ws`, `https`→`wss`) so a
 *  page served over TLS never opens a plaintext socket. An absolute `ws(s)://`
 *  base passes through unchanged; an absolute `http(s)://` base — a plausible
 *  mistake given the sibling variable — has its scheme corrected rather than
 *  left to fail opaquely inside the WebSocket constructor. */
export function resolveWsBase(
  raw: string,
  loc: Pick<Location, "protocol" | "host"> = window.location,
): string {
  const trimmed = raw.replace(/\/+$/, "");
  if (ABSOLUTE_WS_URL.test(trimmed)) {
    return trimmed;
  }
  if (ABSOLUTE_URL.test(trimmed)) {
    return trimmed.replace(/^http/i, "ws");
  }
  const scheme = loc.protocol === "https:" ? "wss" : "ws";
  const path = trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
  return `${scheme}://${loc.host}${path}`;
}

export interface Endpoints {
  /** `market-data`, for candles — a range read and the subscription — and,
   *  proxied through it, `capital-gateway`'s instrument catalogue. One
   *  address for both, because the browser cannot reach the gateway on its
   *  own any more. */
  archiveHttp: string;
  archiveWs: string;
  /** The workbench: the conversation and its cost, and the team catalogue, the model
   *  catalogue and a run's progress. **One address for both**, because they are one
   *  process — two were two modules on two hosts, and there is one host now.
   *
   *  Its own address rather than a path under the archive's: Static Web Apps cannot proxy
   *  a stream any more than it can a WebSocket, so it gets the same split treatment as the
   *  archive. No WS counterpart: both a turn and a run's progress ride plain HTTP
   *  (`fetch` + `ReadableStream`), not a socket. */
  workbenchHttp: string;
  /** `polymarket-data`, for the prediction-market archive: what is tracked, the last
   *  probability of every tracked outcome in one request, an outcome's series and its
   *  changes over a window. Its own address for the same reason the workbench has one —
   *  it is a different App Service behind a different gate — and its own scope, because
   *  it accepts only its own audience. */
  polymarketHttp: string;
  /** `capital-gateway`, for the account: which demo accounts exist, what is open on the
   *  active one, and the demo money on it.
   *
   *  It used to have no address here at all — the gateway was reachable only from two
   *  service addresses, and the instrument catalogue came through market-data for exactly
   *  that reason. It still does; what changed is that the gateway now also recognises an
   *  authenticated browser and lets it reach the account and nothing else
   *  (`capital_gateway/caller_access.py`). In dev this is a prefix the dev server proxies,
   *  because the shared key must not travel to a browser. */
  gatewayHttp: string;
}

// Same defaults as .env.example: a checkout without one falls back to the dev proxy
// rather than crashing the moment a source is built. The `-api` suffix keeps the prefix
// clear of the tab routes — a back end answering a prefix a tab also claims shadows that
// tab — and a test compares it against the route list so a future prefix cannot repeat
// the mistake. See the note in vite.config.ts.
const DEFAULT_ARCHIVE_HTTP = "/archive-api";
const DEFAULT_ARCHIVE_WS = "/archive-api/ws";
const DEFAULT_WORKBENCH_HTTP = "/workbench-api";
const DEFAULT_GATEWAY_HTTP = "/gateway-api";
const DEFAULT_POLYMARKET_HTTP = "/polymarket-api";

export interface EnvVars {
  VITE_ARCHIVE_HTTP?: string;
  VITE_ARCHIVE_WS?: string;
  VITE_WORKBENCH_HTTP?: string;
  VITE_GATEWAY_HTTP?: string;
  VITE_POLYMARKET_HTTP?: string;
  VITE_ENTRA_CLIENT_ID?: string;
  VITE_ENTRA_TENANT_ID?: string;
  VITE_ENTRA_SCOPE?: string;
  VITE_ENTRA_SCOPE_WORKBENCH?: string;
  VITE_ENTRA_SCOPE_GATEWAY?: string;
  VITE_ENTRA_SCOPE_POLYMARKET?: string;
}

/** One scope per module the terminal calls, because each stands behind its own gate and
 *  accepts a token minted for its **own** audience. Entra will only mint one for a
 *  resource asked for by name, so this is what the terminal has to know per back end.
 *
 *  `archive` keeps `VITE_ENTRA_SCOPE`'s plain name — it was the only one when there was
 *  only one — and is the one required scope: it is also what the sign-in redirect asks
 *  for. The other three are optional, and their absence means that module is called with
 *  no credential rather than with the archive's (terminal-identity, "Dwa moduły o różnych
 *  publicznościach"). Sending one module's token to another is what this type exists to
 *  stop; a silent fallback would put it straight back. */
export interface ModuleScopes {
  archive: string;
  workbench: string | null;
  gateway: string | null;
  polymarket: string | null;
}

/** Which Entra registration the terminal signs the operator in against, and what it asks
 *  a token *for* — per module, never one token for all of them. */
export interface EntraConfig {
  clientId: string;
  tenantId: string;
  scopes: ModuleScopes;
}

/**
 * The identity configuration, or `null` when there is none.
 *
 * `null` is a working mode, not a misconfiguration. Locally the archive runs on
 * the same machine with nothing in front of it, and a terminal that demanded a
 * sign-in before it would start would make `pnpm dev` depend on a tenant. All
 * three values or none: two out of three is a typo, and starting anyway would
 * turn it into a sign-in that fails much later with a message about audiences.
 */
export function resolveEntra(env: EnvVars = import.meta.env): EntraConfig | null {
  const clientId = env.VITE_ENTRA_CLIENT_ID?.trim();
  const tenantId = env.VITE_ENTRA_TENANT_ID?.trim();
  const scope = env.VITE_ENTRA_SCOPE?.trim();

  if (!clientId && !tenantId && !scope) return null;
  if (!clientId || !tenantId || !scope) {
    throw new Error(
      "VITE_ENTRA_CLIENT_ID, VITE_ENTRA_TENANT_ID and VITE_ENTRA_SCOPE must be set together " +
        "or left out together — a partial set cannot sign anyone in.",
    );
  }
  // The three per-module scopes are each optional on their own, unlike the triple above:
  // a module with no scope is called with no credential, which its own gate then refuses
  // in a way the tab can name. That is deliberately not the same as reaching for the
  // archive's token, which would be the terminal telling four gates the same thing.
  return {
    clientId,
    tenantId,
    scopes: {
      archive: scope,
      workbench: env.VITE_ENTRA_SCOPE_WORKBENCH?.trim() || null,
      gateway: env.VITE_ENTRA_SCOPE_GATEWAY?.trim() || null,
      polymarket: env.VITE_ENTRA_SCOPE_POLYMARKET?.trim() || null,
    },
  };
}

export function resolveEndpoints(
  env: EnvVars = import.meta.env,
  loc: Pick<Location, "protocol" | "host"> = window.location,
): Endpoints {
  return {
    archiveHttp: resolveHttpBase(env.VITE_ARCHIVE_HTTP || DEFAULT_ARCHIVE_HTTP),
    archiveWs: resolveWsBase(env.VITE_ARCHIVE_WS || DEFAULT_ARCHIVE_WS, loc),
    workbenchHttp: resolveHttpBase(env.VITE_WORKBENCH_HTTP || DEFAULT_WORKBENCH_HTTP),
    gatewayHttp: resolveHttpBase(env.VITE_GATEWAY_HTTP || DEFAULT_GATEWAY_HTTP),
    polymarketHttp: resolveHttpBase(env.VITE_POLYMARKET_HTTP || DEFAULT_POLYMARKET_HTTP),
  };
}
