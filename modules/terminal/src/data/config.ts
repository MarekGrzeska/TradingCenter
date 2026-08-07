/**
 * Two independent base addresses, each accepting a relative path or a full URL —
 * see design.md, "Azure Static Web Apps poda statyki, ale nie przeprowadzi
 * strumienia". Static Web Apps can't proxy the WebSocket, so whatever topology
 * the app ends up deployed behind, HTTP and WS may need to point at different
 * hosts. This is the only place that decision gets made.
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

export interface GatewayEndpoints {
  httpBase: string;
  wsBase: string;
}

// Same defaults as .env.example — a missing .env (a fresh checkout that
// hasn't copied it yet, or a test/CI environment with no env file at all)
// must fall back to "talk to the dev proxy", not crash the moment a gateway
// source is built.
const DEFAULT_HTTP_BASE = "/api";
const DEFAULT_WS_BASE = "/ws";

export function resolveGatewayEndpoints(
  env: { VITE_GATEWAY_HTTP?: string; VITE_GATEWAY_WS?: string } = import.meta.env,
  loc: Pick<Location, "protocol" | "host"> = window.location,
): GatewayEndpoints {
  return {
    httpBase: resolveHttpBase(env.VITE_GATEWAY_HTTP || DEFAULT_HTTP_BASE),
    wsBase: resolveWsBase(env.VITE_GATEWAY_WS || DEFAULT_WS_BASE, loc),
  };
}
