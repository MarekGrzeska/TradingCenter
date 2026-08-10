import { noIdentity, SignedOut, SIGNED_OUT_MESSAGE, type Identity } from "../auth/identity";
import { MarketDataError } from "./types";

/**
 * The one place an HTTP failure becomes something an operator can read.
 *
 * Both back ends the terminal talks to are FastAPI, so both spell a refusal the
 * same two ways — a `detail` string, or the framework's own list of validation
 * objects — and neither is worth parsing twice. What they do *not* share is
 * what a status means: 422 is an unsupported resolution to the gateway and a
 * pair the archive will not take on. That judgement stays with each adapter,
 * which is what `mapStatus` is.
 */

export interface JsonRequest {
  signal: AbortSignal;
  method?: "GET" | "POST" | "DELETE";
  body?: unknown;
}

export type StatusMapper = (status: number, detail: string) => MarketDataError;

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
 * An HTTP client for one back end: `label` names it in the one message it composes
 * itself, and `mapStatus` decides what its refusals mean.
 *
 * Attaching the credential is this function's job rather than each call site's, and that
 * is load-bearing: a route added to `archive.ts` or `gatewaySource.ts` later carries a
 * token because it cannot not carry one. Neither file mentions a token anywhere. Left
 * out, `identity` is the one with none — local mode, requests go out bare.
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

    // One retry, and exactly one. A token can expire between being read from
    // the cache and reaching the archive, and renewing it silently is better
    // than showing the operator a failure they can do nothing about. Bounding
    // it at a single attempt is what keeps "refused → renew → refused" from
    // becoming a loop that hammers both the archive and the token endpoint.
    if (response.status === UNAUTHENTICATED && token !== null) {
      try {
        token = await identity.refresh();
      } catch (cause) {
        throw asUnauthenticated(cause);
      }
      response = await attempt(url, request, token);
    }

    if (response.status === UNAUTHENTICATED) {
      // Survived the renewal, so it is the session and not the token. The
      // detail from the server is dropped on purpose: it describes an audience
      // or an issuer, and the operator's move is the same either way.
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

/** `SignedOut` from the identity layer, said in the data layer's own vocabulary
 *  so no caller has to know both. Anything else — the token endpoint being
 *  briefly unreachable — is not a signed-out session and passes through
 *  untouched, because retrying is the right answer to it and is not the right
 *  answer to the other. */
function asUnauthenticated(cause: unknown): unknown {
  return cause instanceof SignedOut
    ? new MarketDataError("unauthenticated", cause.message)
    : cause;
}
