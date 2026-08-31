/**
 * Where an HTTP failure becomes something the operator can read on a phone. What a status *means* stays
 * with the caller (`kinds`): 409 is the tracking ceiling here and would be something else anywhere else.
 */

export type FailureKind = "unreachable" | "refused" | "not-found" | "upstream" | "unknown";

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
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
}

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

export function jsonClient(label: string, kinds: Partial<Record<number, FailureKind>>) {
  async function send(url: string, request: JsonRequest): Promise<Response> {
    let response: Response;
    try {
      response = await fetch(url, {
        method: request.method ?? "GET",
        signal: request.signal,
        headers: {
          Accept: "application/json",
          ...(request.body === undefined ? {} : { "Content-Type": "application/json" }),
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
