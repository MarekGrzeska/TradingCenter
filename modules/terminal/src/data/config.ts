/**
 * Where the archive lives, as a relative path or a full URL. HTTP and WebSocket are configured separately
 * because Static Web Apps cannot proxy the socket (design.md), so the two may need different hosts.
 */

const ABSOLUTE_URL = /^https?:\/\//i;
const ABSOLUTE_WS_URL = /^wss?:\/\//i;

/** A relative HTTP path needs no expansion — `fetch("/api/x")` already
 *  resolves against the page origin. Only trims a trailing slash so callers can
 *  join paths with a plain template string. */
export function resolveHttpBase(raw: string): string {
  return raw.replace(/\/+$/, "");
}

/** `new WebSocket("/ws")` throws — a WebSocket URL must be absolute — so a relative base is expanded against
 *  the page's origin, upgrading the scheme so a page served over TLS never opens a plaintext socket. */
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
  /** The workbench: the conversation, its cost, the catalogues and a run's progress. **One address**, because
   *  they are one process. Its own rather than a path under the archive's, since SWA cannot proxy a stream. */
  workbenchHttp: string;
  /** `polymarket-data`, for the prediction-market archive. Its own address for the reason the workbench has
   *  one — a different App Service behind a different gate — and its own scope: it accepts only its audience. */
  polymarketHttp: string;
  /** `strategy`, for the strategy platform: the catalogue of entries, which pairs are
   *  watched, every decision with the reason it carries, and the backtest reports that
   *  were kept. Its own address and its own scope for the same reason as the two above —
   *  a different App Service behind a different gate. */
  strategyHttp: string;
  /** `social-data`, for the posts: the archive of what was said and what a model made of it.
   *  Its own address and its own scope, for the reason the two above have theirs. */
  socialHttp: string;
  /** `capital-gateway`, for the account. It used to have no address here at all; what changed is that the
   *  gateway recognises an authenticated browser. In dev this is a prefix the dev server proxies. */
  gatewayHttp: string;
}

// Same defaults as .env.example, so a checkout without one falls back to the dev proxy. The `-api` suffix
// keeps the prefix clear of the tab routes — a back end answering a tab's prefix shadows that tab.
const DEFAULT_ARCHIVE_HTTP = "/archive-api";
const DEFAULT_ARCHIVE_WS = "/archive-api/ws";
const DEFAULT_WORKBENCH_HTTP = "/workbench-api";
const DEFAULT_GATEWAY_HTTP = "/gateway-api";
const DEFAULT_POLYMARKET_HTTP = "/polymarket-api";
const DEFAULT_STRATEGY_HTTP = "/strategy-api";
const DEFAULT_SOCIAL_HTTP = "/social-api";

export interface EnvVars {
  VITE_ARCHIVE_HTTP?: string;
  VITE_ARCHIVE_WS?: string;
  VITE_WORKBENCH_HTTP?: string;
  VITE_GATEWAY_HTTP?: string;
  VITE_POLYMARKET_HTTP?: string;
  VITE_STRATEGY_HTTP?: string;
  VITE_SOCIAL_HTTP?: string;
  VITE_ENTRA_CLIENT_ID?: string;
  VITE_ENTRA_TENANT_ID?: string;
  VITE_ENTRA_SCOPE?: string;
  VITE_ENTRA_SCOPE_WORKBENCH?: string;
  VITE_ENTRA_SCOPE_GATEWAY?: string;
  VITE_ENTRA_SCOPE_POLYMARKET?: string;
  VITE_ENTRA_SCOPE_STRATEGY?: string;
  VITE_ENTRA_SCOPE_SOCIAL?: string;
}

/** One scope per module, because each accepts a token minted for its **own** audience. `archive` keeps
 *  `VITE_ENTRA_SCOPE`'s plain name and is the required one; the rest absent means no credential, not this one. */
export interface ModuleScopes {
  archive: string;
  workbench: string | null;
  gateway: string | null;
  polymarket: string | null;
  strategy: string | null;
  social: string | null;
}

/** Which Entra registration the terminal signs the operator in against, and what it asks
 *  a token *for* — per module, never one token for all of them. */
export interface EntraConfig {
  clientId: string;
  tenantId: string;
  scopes: ModuleScopes;
}

/**
 * `null` is a working mode: locally the archive has nothing in front of it, and demanding a sign-in would make
 * `pnpm dev` depend on a tenant. All three values or none — two is a typo that fails much later.
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
  // Each per-module scope is optional on its own: a module with no scope is called with no credential, which
  // its gate refuses in a way the tab can name. Reaching for the archive's token would tell five gates one thing.
  return {
    clientId,
    tenantId,
    scopes: {
      archive: scope,
      workbench: env.VITE_ENTRA_SCOPE_WORKBENCH?.trim() || null,
      gateway: env.VITE_ENTRA_SCOPE_GATEWAY?.trim() || null,
      polymarket: env.VITE_ENTRA_SCOPE_POLYMARKET?.trim() || null,
      strategy: env.VITE_ENTRA_SCOPE_STRATEGY?.trim() || null,
      social: env.VITE_ENTRA_SCOPE_SOCIAL?.trim() || null,
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
    strategyHttp: resolveHttpBase(env.VITE_STRATEGY_HTTP || DEFAULT_STRATEGY_HTTP),
    socialHttp: resolveHttpBase(env.VITE_SOCIAL_HTTP || DEFAULT_SOCIAL_HTTP),
  };
}
