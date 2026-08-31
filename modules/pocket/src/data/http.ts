/**
 * Where an HTTP failure becomes something the operator can read on a phone. What a status *means* stays
 * with the caller (`kinds`): 409 is the tracking ceiling here and would be something else anywhere else.
 */

import { noIdentity, SignedOut, SIGNED_OUT_MESSAGE, type Identity } from "../auth/identity";

export type FailureKind =
  | "unreachable"
  | "unauthenticated"
  | "refused"
  | "not-found"
  | "upstream"
  | "unknown";

export class ArchiveError extends Error {
  readonly kind: FailureKind;

  constructor(kind: FailureKind, message: string) {
    super(message);
    this.name = "ArchiveError";
    this.kind = kind;
  }
}

export interface JsonRequest {
  signal: AbortSignal;
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
}

/** The status that means "not you" rather than "not that", and the one status whose meaning does not
 *  vary with the route — which is why it is handled here and never in a caller's table. */
const UNAUTHENTICATED = 401;

async function errorDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") {
      return body.detail;
    }
    // FastAPI's own validation-error shape is a list of {loc, msg, type}, not a plain string.
    if (Array.isArray(body.detail)) {
      return body.detail
        .map((entry) => (entry && typeof entry === "object" && "msg" in entry ? entry.msg : entry))
        .join("; ");
    }
  } catch {
    /* not JSON, or no body — the status line below says it instead */
  }
  return response.statusText || `HTTP ${response.status}`;
}

/**
 * A client for one back end. Attaching the credential here rather than at each call site is
 * load-bearing: a route added later carries a token because it cannot not carry one. No `identity`
 * means the local stack, where the archive requires no principal and the request goes out bare.
 */
export function jsonClient(
  label: string,
  kinds: Partial<Record<number, FailureKind>>,
  identity: Identity = noIdentity,
) {
  async function attempt(url: string, request: JsonRequest, token: string | null) {
    try {
      return await fetch(url, {
        method: request.method ?? "GET",
        signal: request.signal,
        headers: {
          Accept: "application/json",
          ...(request.body === undefined ? {} : { "Content-Type": "application/json" }),
          ...(token === null ? {} : { Authorization: `Bearer ${token}` }),
        },
        ...(request.body === undefined ? {} : { body: JSON.stringify(request.body) }),
      });
    } catch (cause) {
      // An abort is the caller's own doing and must stay distinguishable from the source being down.
      if (request.signal.aborted) {
        throw cause;
      }
      throw new ArchiveError("unreachable", `${label} is not reachable`);
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

    // One retry, and exactly one: a token can expire between the cache and the archive, and bounding
    // it at a single attempt keeps "refused → renew → refused" from hammering both.
    if (response.status === UNAUTHENTICATED && token !== null) {
      try {
        token = await identity.refresh();
      } catch (cause) {
        throw asUnauthenticated(cause);
      }
      response = await attempt(url, request, token);
    }

    if (response.status === UNAUTHENTICATED) {
      // Survived the renewal, so it is the session and not the token. The server's detail is dropped:
      // it describes an audience or an issuer, and the operator's move is the same either way.
      throw new ArchiveError("unauthenticated", SIGNED_OUT_MESSAGE);
    }
    if (!response.ok) {
      throw new ArchiveError(kinds[response.status] ?? "unknown", await errorDetail(response));
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

/** `SignedOut` said in this layer's own vocabulary, so no caller has to know both. Anything else — the
 *  token endpoint briefly unreachable — passes through untouched, because retrying is right for that. */
function asUnauthenticated(cause: unknown): unknown {
  return cause instanceof SignedOut ? new ArchiveError("unauthenticated", cause.message) : cause;
}
