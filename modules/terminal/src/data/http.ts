import { noIdentity, SignedOut, SIGNED_OUT_MESSAGE, type Identity } from "../auth/identity";
import { MarketDataError, type MarketDataErrorKind } from "./types";

/**
 * Where an HTTP failure becomes something an operator can read. What a status *means* stays with each adapter,
 * which is what `mapStatus` is: 422 is an unsupported resolution to the gateway, a refused pair to the archive.
 */

export interface JsonRequest {
  signal: AbortSignal;
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
}

export type StatusMapper = (status: number, detail: string) => MarketDataError;

/**
 * A back end's refusals, as a table: every adapter answered the same question with the same four `if`s, and the
 * differences are the content. 401 is nobody's to list — `jsonClient` handles it before this is reached.
 */
export function statusMapper(kinds: Partial<Record<number, MarketDataErrorKind>>): StatusMapper {
  return (status, detail) => new MarketDataError(kinds[status] ?? "unknown", detail);
}

async function parseErrorDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") {
      return body.detail;
    }
    // FastAPI's own validation-error shape (a 422 from a bad query param) is a
    // list of {loc, msg, type} objects, not a plain string.
    if (Array.isArray(body.detail)) {
      return body.detail
        .map((entry) => (entry && typeof entry === "object" && "msg" in entry ? entry.msg : entry))
        .join("; ");
    }
  } catch {
    // Not JSON, or no body — fall through to the status line below.
  }
  return response.statusText || `HTTP ${response.status}`;
}

/** The status that means "not you" rather than "not that". Both back ends are
 *  the same deployment behind the same authenticator, so unlike every other
 *  status this one means the same thing whichever adapter asked — which is why
 *  it is handled here and not in a `mapStatus`. */
const UNAUTHENTICATED = 401;

/**
 * An HTTP client for one back end. Attaching the credential here rather than at each call site is load-bearing:
 * a route added later carries a token because it cannot not carry one. No `identity` means local mode, bare.
 */
export function jsonClient(label: string, mapStatus: StatusMapper, identity: Identity = noIdentity) {
  async function attempt(url: string, request: JsonRequest, token: string | null) {
    try {
      return await fetch(url, {
        method: request.method ?? "GET",
        signal: request.signal,
        headers: {
          ...(request.body === undefined ? {} : { "Content-Type": "application/json" }),
          ...(token === null ? {} : { Authorization: `Bearer ${token}` }),
        },
        ...(request.body === undefined ? {} : { body: JSON.stringify(request.body) }),
      });
    } catch (cause) {
      // An abort is the caller's own doing and must stay distinguishable from
      // the source being down — it is rethrown as-is.
      if (request.signal.aborted) {
        throw cause;
      }
      throw new MarketDataError("unreachable", `${label} is not reachable`);
    }
  }

  async function send(url: string, request: JsonRequest): Promise<Response> {
    let token: string | null;
    try {
      token = await identity.token();
    } catch (cause) {
      throw asUnauthenticated(cause);
    }

    let response = await attempt(url, request, token);

    // One retry, and exactly one: a token can expire between the cache and the archive, and bounding it at a
    // single attempt keeps "refused → renew → refused" from hammering both the archive and the token endpoint.
    if (response.status === UNAUTHENTICATED && token !== null) {
      try {
        token = await identity.refresh();
      } catch (cause) {
        throw asUnauthenticated(cause);
      }
      response = await attempt(url, request, token);
    }

    if (response.status === UNAUTHENTICATED) {
      // Survived the renewal, so it is the session and not the token. The server's detail is dropped: it
      // describes an audience or an issuer, and the operator's move is the same either way.
      throw new MarketDataError("unauthenticated", SIGNED_OUT_MESSAGE);
    }
    if (!response.ok) {
      throw mapStatus(response.status, await parseErrorDetail(response));
    }
    return response;
  }

  return {
    send,
    async json<T>(url: string, request: JsonRequest): Promise<T> {
      return (await send(url, request)).json() as Promise<T>;
    },
  };
}

/** `SignedOut` said in the data layer's own vocabulary, so no caller has to know both. Anything else — the token
 *  endpoint briefly unreachable — passes through untouched, because retrying is the right answer to that one. */
function asUnauthenticated(cause: unknown): unknown {
  return cause instanceof SignedOut
    ? new MarketDataError("unauthenticated", cause.message)
    : cause;
}
