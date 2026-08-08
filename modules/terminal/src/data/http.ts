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

/** An HTTP client for one back end: `label` names it in the one message it has
 *  to compose itself, and `mapStatus` decides what its refusals mean. */
export function jsonClient(label: string, mapStatus: StatusMapper) {
  async function send(url: string, request: JsonRequest): Promise<Response> {
    let response: Response;
    try {
      response = await fetch(url, {
        method: request.method ?? "GET",
        signal: request.signal,
        ...(request.body === undefined
          ? {}
          : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(request.body) }),
      });
    } catch (cause) {
      // An abort is the caller's own doing and must stay distinguishable from
      // the source being down — it is rethrown as-is.
      if (request.signal.aborted) {
        throw cause;
      }
      throw new MarketDataError("unreachable", `${label} is not reachable`);
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
