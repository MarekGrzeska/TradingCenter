import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { SignedOut, noIdentity, type Identity } from "../auth/identity";
import { http, HttpResponse, setupServer } from "../test/httpDouble";
import { jsonClient } from "./http";
import { MarketDataError } from "./types";

/**
 * `terminal-identity` spec tests, here rather than beside an adapter on purpose: the point of attaching the
 * token in one place is that no adapter has to be trusted to do it, including the one written next year.
 */

const BASE = "http://archive.test";
const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

/** An identity that hands out whatever tokens the test names, in order, and
 *  counts how often it was asked for a fresh one. */
function identityOf(...tokens: (string | SignedOut)[]): Identity & { refreshes: number } {
  let next = 0;
  const state = {
    refreshes: 0,
    state: () => "signed-in" as const,
    subscribe: () => () => {},
    async token() {
      const value = tokens[Math.min(next, tokens.length - 1)];
      next += 1;
      if (value instanceof SignedOut) throw value;
      return value;
    },
    async refresh() {
      state.refreshes += 1;
      return state.token();
    },
    signIn: () => {},
  };
  return state;
}

const mapStatus = (status: number, detail: string) =>
  new MarketDataError(status === 404 ? "not-found" : "unknown", detail);

function client(identity?: Identity) {
  return jsonClient("the candle archive", mapStatus, identity);
}

function signal() {
  return new AbortController().signal;
}

describe("jsonClient and the operator's credential", () => {
  it("carries the token on every request, whatever the route", async () => {
    const seen: (string | null)[] = [];
    server.use(
      http.get(`${BASE}/candles/US100`, ({ request }) => {
        seen.push(request.headers.get("Authorization"));
        return HttpResponse.json({ ok: true });
      }),
      // The route nobody has written yet, standing in for every route added later — it carries the token
      // because the client does, not because whoever writes it remembers to.
      http.get(`${BASE}/something-new`, ({ request }) => {
        seen.push(request.headers.get("Authorization"));
        return HttpResponse.json({ ok: true });
      }),
    );

    const api = client(identityOf("a-token"));
    await api.json(`${BASE}/candles/US100`, { signal: signal() });
    await api.json(`${BASE}/something-new`, { signal: signal() });

    expect(seen).toEqual(["Bearer a-token", "Bearer a-token"]);
  });

  it("sends no credential at all when none is configured", async () => {
    let header: string | null = "not asked";
    server.use(
      http.get(`${BASE}/health`, ({ request }) => {
        header = request.headers.get("Authorization");
        return HttpResponse.json({});
      }),
    );

    await client(noIdentity).json(`${BASE}/health`, { signal: signal() });

    expect(header).toBeNull();
  });

  it("renews the token once and retries, when a refusal is the token's age", async () => {
    let calls = 0;
    const seen: (string | null)[] = [];
    server.use(
      http.get(`${BASE}/pairs`, ({ request }) => {
        seen.push(request.headers.get("Authorization"));
        calls += 1;
        return calls === 1
          ? new Response(null, { status: 401 })
          : HttpResponse.json([{ symbol: "US100" }]);
      }),
    );
    const identity = identityOf("stale-token", "fresh-token");

    const body = await client(identity).json(`${BASE}/pairs`, { signal: signal() });

    expect(body).toEqual([{ symbol: "US100" }]);
    expect(seen).toEqual(["Bearer stale-token", "Bearer fresh-token"]);
    expect(identity.refreshes).toBe(1);
  });

  it("gives up after one renewal rather than looping between refusal and renewal", async () => {
    let calls = 0;
    server.use(
      http.get(`${BASE}/pairs`, () => {
        calls += 1;
        return new Response(null, { status: 401 });
      }),
    );
    const identity = identityOf("stale-token", "also-stale");

    await expect(client(identity).json(`${BASE}/pairs`, { signal: signal() })).rejects.toMatchObject(
      { kind: "unauthenticated" },
    );

    expect(calls).toBe(2); // the original and exactly one retry
    expect(identity.refreshes).toBe(1);
  });

  it("says the operator is signed out rather than that the archive is unreachable", async () => {
    server.use(http.get(`${BASE}/pairs`, () => new Response(null, { status: 401 })));

    const failure = await client(identityOf(new SignedOut()))
      .json(`${BASE}/pairs`, { signal: signal() })
      .catch((cause: unknown) => cause);

    expect(failure).toBeInstanceOf(MarketDataError);
    expect((failure as MarketDataError).kind).toBe("unauthenticated");
    // Not "unreachable": the archive is fine and does not know who is asking,
    // and sending an operator to look at Azure for that would waste their day.
    expect((failure as MarketDataError).message).toMatch(/sign in/i);
  });

  it("never quotes the credential back in a message", async () => {
    server.use(
      http.get(`${BASE}/pairs`, () => HttpResponse.json({ detail: "nope" }, { status: 404 })),
    );

    const failure = (await client(identityOf("a-very-secret-token"))
      .json(`${BASE}/pairs`, { signal: signal() })
      .catch((cause: unknown) => cause)) as MarketDataError;

    expect(failure.message).not.toContain("a-very-secret-token");
  });

  it("leaves a token endpoint that is merely down as something to retry", async () => {
    // Not a `SignedOut`: the session may be good and the network briefly not. Reporting it as signed out
    // sends the operator through a sign-in they did not need and may not be able to complete.
    const flaky: Identity = {
      ...noIdentity,
      token: async () => {
        throw new Error("the token endpoint is not reachable");
      },
    };

    await expect(
      client(flaky).json(`${BASE}/pairs`, { signal: signal() }),
    ).rejects.not.toBeInstanceOf(MarketDataError);
  });
});
