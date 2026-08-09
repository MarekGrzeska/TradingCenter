/**
 * Where the archive lives — the one back end the terminal now holds an
 * address for — accepting a relative path or a full URL.
 *
 * HTTP and WebSocket are configured separately — see design.md, "Azure Static
 * Web Apps poda statyki, ale nie przeprowadzi strumienia". Static Web Apps
 * can't proxy the WebSocket, so whatever topology the app ends up deployed
 * behind, the two may need to point at different hosts.
 *
 * `capital-gateway` has no address here at all. It never got a WebSocket one —
 * the stream the terminal used to open there comes from the archive instead —
 * and it lost its HTTP one too, once the gateway stopped being reachable from
 * a browser: the instrument catalogue now comes through the archive, which
 * proxies it (`gatewaySource.ts`, `marketData.ts`). This is the only place any
 * of those decisions gets made.
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
}

// Same defaults as .env.example — a missing .env (a fresh checkout that
// hasn't copied it yet, or a test/CI environment with no env file at all)
// must fall back to "talk to the dev proxy", not crash the moment a source is
// built.
// The `-api` suffix keeps this prefix clear of the tab routes: a back end
// answering a prefix a tab also claims shadows that tab for every request which
// actually reaches a server. A test compares it against the route list so a
// future prefix cannot repeat the mistake. See the note in vite.config.ts.
const DEFAULT_ARCHIVE_HTTP = "/archive-api";
const DEFAULT_ARCHIVE_WS = "/archive-api/ws";

export interface EnvVars {
  VITE_ARCHIVE_HTTP?: string;
  VITE_ARCHIVE_WS?: string;
  VITE_ENTRA_CLIENT_ID?: string;
  VITE_ENTRA_TENANT_ID?: string;
  VITE_ENTRA_SCOPE?: string;
}

/** Which Entra registration the terminal signs the operator in against, and
 *  what it asks a token *for*. The scope names the archive, not the terminal:
 *  the token is presented to `market-data`, and Entra will only mint one for a
 *  resource that was asked for by name. */
export interface EntraConfig {
  clientId: string;
  tenantId: string;
  scope: string;
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
  return { clientId, tenantId, scope };
}

export function resolveEndpoints(
  env: EnvVars = import.meta.env,
  loc: Pick<Location, "protocol" | "host"> = window.location,
): Endpoints {
  return {
    archiveHttp: resolveHttpBase(env.VITE_ARCHIVE_HTTP || DEFAULT_ARCHIVE_HTTP),
    archiveWs: resolveWsBase(env.VITE_ARCHIVE_WS || DEFAULT_ARCHIVE_WS, loc),
  };
}
