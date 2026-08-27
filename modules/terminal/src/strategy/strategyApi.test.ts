import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { MarketDataError } from "../data/types";
import { http, HttpResponse, setupServer } from "../test/httpDouble";
import { createStrategyApi } from "./strategyApi";

/**
 * The wire↔domain seam. The tests that matter most are about **refusals**: a 422 is the module declining a request it
 * understood, a 504 the module saying it could not see the archive — which is not the same as seeing nothing.
 */

const HTTP_BASE = "http://strategy.test";

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function api() {
  return createStrategyApi(HTTP_BASE);
}

function signal() {
  return new AbortController().signal;
}

const REFUSAL = {
  id: 11,
  strategy_id: "baseline_ma_cross",
  symbol: "US100",
  parameter_set_id: 3,
  as_of: "2026-08-22T10:00:00Z",
  action: "no_trade",
  reason: "the fast average did not cross above the slow one on this bar",
  reason_kind: "strategy",
  direction: null,
  entry: null,
  stop: null,
  target: null,
  rr: null,
  score: null,
  features: { separation_atr: 0.4 },
  created_at: "2026-08-22T11:00:05Z",
};

const SETUP = {
  ...REFUSAL,
  id: 12,
  action: "trade",
  reason: "the fast average crossed above the slow one",
  reason_kind: null,
  direction: "long",
  entry: 100.5,
  stop: 98.5,
  target: 106.5,
  rr: 3,
  score: 82.5,
};

describe("reading decisions", () => {
  it("asks for both kinds by default", async () => {
    // The default is the whole point of this screen: a list of setups alone is empty on
    // exactly the days somebody is asking why nothing happened.
    let asked: string | null = null;
    server.use(
      http.get(`${HTTP_BASE}/decisions`, ({ request }) => {
        asked = new URL(request.url).searchParams.get("action");
        return HttpResponse.json([REFUSAL, SETUP]);
      }),
    );

    const decisions = await api().listDecisions(signal());

    expect(asked).toBeNull();
    expect(decisions).toHaveLength(2);
  });

  it("carries the reason and its kind through the seam", async () => {
    server.use(http.get(`${HTTP_BASE}/decisions`, () => HttpResponse.json([REFUSAL])));

    const [decision] = await api().listDecisions(signal());

    expect(decision.action).toBe("no_trade");
    expect(decision.reasonKind).toBe("strategy");
    expect(decision.reason).toContain("did not cross");
    expect(decision.asOf).toEqual(new Date("2026-08-22T10:00:00Z"));
  });

  it("keeps a setup's levels apart from a refusal's absent ones", async () => {
    server.use(http.get(`${HTTP_BASE}/decisions`, () => HttpResponse.json([SETUP])));

    const [decision] = await api().listDecisions(signal());

    expect(decision.entry).toBe(100.5);
    expect(decision.rr).toBe(3);
    expect(decision.reasonKind).toBeNull();
  });

  it("narrows to one strategy when asked", async () => {
    let asked: string | null = null;
    server.use(
      http.get(`${HTTP_BASE}/decisions`, ({ request }) => {
        asked = new URL(request.url).searchParams.get("strategy_id");
        return HttpResponse.json([]);
      }),
    );

    await api().listDecisions(signal(), { strategyId: "baseline_ma_cross" });

    expect(asked).toBe("baseline_ma_cross");
  });
});

describe("when the module declines", () => {
  it("a parameter out of range is a refusal carrying the parameter's name", async () => {
    server.use(
      http.post(`${HTTP_BASE}/parameter-sets`, () =>
        HttpResponse.json(
          { detail: "parameter 'fast_period' = 9999 is outside [2, 200]" },
          { status: 422 },
        ),
      ),
    );

    const failure = await api()
      .addParameterSet("baseline_ma_cross", { fast_period: 9999 }, signal())
      .catch((error: unknown) => error);

    expect(failure).toBeInstanceOf(MarketDataError);
    expect((failure as MarketDataError).kind).toBe("refused");
    expect((failure as MarketDataError).message).toContain("fast_period");
  });

  it("a module that could not see the archive is upstream, not empty", async () => {
    // The distinction the module itself makes: it says it could not read, rather than
    // answering with no decisions — and the tab must not flatten that into "nothing found".
    server.use(
      http.get(`${HTTP_BASE}/decisions`, () =>
        HttpResponse.json({ detail: "the archive did not answer" }, { status: 504 }),
      ),
    );

    const failure = await api()
      .listDecisions(signal())
      .catch((error: unknown) => error);

    expect((failure as MarketDataError).kind).toBe("upstream");
  });

  it("a caller with no business on the REST contract is refused, not signed out", async () => {
    server.use(
      http.get(`${HTTP_BASE}/strategies`, () =>
        HttpResponse.json({ detail: "this caller has no access to rest" }, { status: 403 }),
      ),
    );

    const failure = await api()
      .listStrategies(signal())
      .catch((error: unknown) => error);

    expect((failure as MarketDataError).kind).toBe("refused");
  });
});

describe("starting a watch", () => {
  it("sends no parameters when none were given", async () => {
    // The module then writes a set from the strategy's own resolved defaults. Sending them
    // from here would make the terminal the author of values it merely displayed.
    let body: unknown = null;
    let wroteParameterSet = false;
    server.use(
      http.post(`${HTTP_BASE}/parameter-sets`, () => {
        wroteParameterSet = true;
        return HttpResponse.json({});
      }),
      http.post(`${HTTP_BASE}/watches`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          id: 1,
          strategy_id: "baseline_ma_cross",
          symbol: "US100",
          parameter_set_id: 5,
          active: true,
          created_at: "2026-08-22T12:00:00Z",
        });
      }),
    );

    const watch = await api().startWatch("baseline_ma_cross", "US100", signal());

    expect(wroteParameterSet).toBe(false);
    expect(body).toEqual({ strategy_id: "baseline_ma_cross", symbol: "US100" });
    expect(watch.active).toBe(true);
  });

  it("writes a parameter set first when values were given", async () => {
    let watchBody: Record<string, unknown> | null = null;
    server.use(
      http.post(`${HTTP_BASE}/parameter-sets`, () =>
        HttpResponse.json({
          id: 9,
          strategy_id: "baseline_ma_cross",
          version: 2,
          params: { fast_period: 8 },
          created_at: "2026-08-22T12:00:00Z",
        }),
      ),
      http.post(`${HTTP_BASE}/watches`, async ({ request }) => {
        watchBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          id: 1,
          strategy_id: "baseline_ma_cross",
          symbol: "US100",
          parameter_set_id: 9,
          active: true,
          created_at: "2026-08-22T12:00:00Z",
        });
      }),
    );

    await api().startWatch("baseline_ma_cross", "US100", signal(), { fast_period: 8 });

    expect(watchBody).not.toBeNull();
    expect(watchBody!.parameter_set_id).toBe(9);
  });
});

describe("stopping a watch", () => {
  it("flips the flag and does not delete anything", async () => {
    let method: string | null = null;
    server.use(
      http.patch(`${HTTP_BASE}/watches/4`, async ({ request }) => {
        method = request.method;
        return HttpResponse.json({
          id: 4,
          strategy_id: "baseline_ma_cross",
          symbol: "US100",
          parameter_set_id: 5,
          active: false,
          created_at: "2026-08-22T12:00:00Z",
        });
      }),
    );

    const watch = await api().setWatchActive(4, false, signal());

    expect(method).toBe("PATCH");
    expect(watch.active).toBe(false);
  });
});
