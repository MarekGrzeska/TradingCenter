/**
 * A stand-in for the slice of `msw` this suite used, backed by swapping
 * `globalThis.fetch`.
 *
 * `msw` stopped intercepting anything on Node 25: a request matching a
 * registered handler hangs instead of answering, so every test that touched
 * HTTP either timed out or reported the back end as unreachable — which reads
 * exactly like the code under test being broken. Its whole job here was to
 * answer a `fetch`, and a test suite does not need a service worker to do that.
 *
 * The shape is deliberately msw's, so the tests that were written against it
 * did not have to be rewritten to say the same things.
 */

type Resolver = (context: { request: Request }) => Response | Promise<Response>;

interface Handler {
  method: string;
  url: string;
  resolve: Resolver;
}

function handler(method: string) {
  return (url: string, resolve: Resolver): Handler => ({ method, url, resolve });
}

export const http = {
  get: handler("GET"),
  post: handler("POST"),
  delete: handler("DELETE"),
  put: handler("PUT"),
};

/** A `Response`, with msw's spelling. `HttpResponse.error()` is a transport
 *  failure — what an unreachable host looks like — rather than a 5xx, which is
 *  a host that answered. */
export class HttpResponse extends Response {
  static json(body: unknown, init: ResponseInit = {}): Response {
    return new Response(JSON.stringify(body), {
      status: 200,
      ...init,
      headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
    });
  }

  static error(): Response {
    // Marked so the swapped fetch can throw it as a transport failure; a real
    // `Response.error()` would arrive at the caller as an answer.
    return Object.assign(new Response(null, { status: 500 }), { __transportFailure: true });
  }
}

export interface MockServer {
  listen(options?: { onUnhandledRequest?: "error" | "warn" | "bypass" }): void;
  use(...handlers: Handler[]): void;
  resetHandlers(): void;
  close(): void;
}

export function setupServer(...initial: Handler[]): MockServer {
  let handlers: Handler[] = [...initial];
  let onUnhandled: "error" | "warn" | "bypass" = "error";
  let original: typeof fetch | undefined;

  const swapped: typeof fetch = async (input, init) => {
    // Deliberately not `new Request(input, init)`. jsdom's `Request` refuses an
    // `AbortSignal` built by the test's own realm, and the resulting throw
    // reaches the adapter as a transport failure — reported as "the back end is
    // not reachable", which is precisely the misleading state this file exists
    // to remove. The two fields a resolver actually reads are built by hand.
    // Resolved against the page, because the app's default addresses are
    // relative (`/api`, `/archive-api`) — what the dev proxy expects — and a
    // handler is written with the origin spelled out.
    const raw = typeof input === "string" ? input : (input as { url: string }).url;
    const url = new URL(raw, globalThis.location?.href ?? "http://localhost").href;
    const method = (init?.method ?? "GET").toUpperCase();
    const body = init?.body;
    const request = {
      url,
      method,
      async json() {
        return typeof body === "string" ? JSON.parse(body) : body;
      },
      async text() {
        return typeof body === "string" ? body : String(body ?? "");
      },
    } as unknown as Request;

    const path = url.split("?")[0];
    const match = handlers.find((h) => h.method === method && path === h.url);

    if (!match) {
      if (onUnhandled === "bypass" && original) {
        return original(input as RequestInfo, init);
      }
      // Thrown rather than answered with a status: a request nobody planned for
      // is a test that has drifted from the code, and a 404 would be quietly
      // absorbed by an adapter that has a meaning for one.
      throw new Error(`unhandled request: ${method} ${url}`);
    }

    const response = await match.resolve({ request });
    if ((response as { __transportFailure?: boolean }).__transportFailure) {
      throw new TypeError("fetch failed");
    }
    return response;
  };

  return {
    listen(options = {}) {
      onUnhandled = options.onUnhandledRequest ?? "error";
      original = globalThis.fetch;
      globalThis.fetch = swapped;
    },
    use(...added: Handler[]) {
      // Prepended, so a later `use` overrides an earlier one for the same route
      // — which is how msw behaves and what a couple of these tests rely on.
      handlers = [...added, ...handlers];
    },
    resetHandlers() {
      handlers = [...initial];
    },
    close() {
      if (original) globalThis.fetch = original;
    },
  };
}
