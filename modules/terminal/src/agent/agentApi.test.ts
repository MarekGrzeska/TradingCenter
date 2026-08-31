import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { http, HttpResponse, setupServer } from "../test/httpDouble";
import { createAgentApi } from "./agentApi";
import { MarketDataError } from "../data/types";

const HTTP_BASE = "http://agent.test";

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function api() {
  return createAgentApi(HTTP_BASE);
}

describe("agentApi.listModels", () => {
  it("maps snake_case models to the terminal's own shape, rates kept as strings", async () => {
    server.use(
      http.get(`${HTTP_BASE}/models`, () =>
        HttpResponse.json([
          {
            id: "gpt-5.6-luna",
            display_name: "Luna",
            cost_rank: 1,
            input_rate_per_1m: "0.2",
            output_rate_per_1m: "1.2",
          },
        ]),
      ),
    );

    const models = await api().listModels(new AbortController().signal);
    expect(models).toEqual([
      {
        id: "gpt-5.6-luna",
        displayName: "Luna",
        costRank: 1,
        inputRatePer1M: "0.2",
        outputRatePer1M: "1.2",
      },
    ]);
  });
});

describe("agentApi.createSession", () => {
  it("posts the chosen model and maps the session back, ISO instants to epoch seconds", async () => {
    let body: unknown;
    server.use(
      http.post(`${HTTP_BASE}/sessions`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(
          {
            id: 7,
            title: null,
            current_model_id: "gpt-5.6-luna",
            created_at: "2026-08-11T10:00:00Z",
            last_active_at: "2026-08-11T10:00:00Z",
          },
          { status: 201 },
        );
      }),
    );

    const session = await api().createSession("gpt-5.6-luna", new AbortController().signal);
    expect(body).toEqual({ model_id: "gpt-5.6-luna" });
    expect(session).toEqual({
      id: 7,
      title: null,
      currentModelId: "gpt-5.6-luna",
      createdAt: 1786442400,
      lastActiveAt: 1786442400,
    });
  });

  it("maps an unknown model id to a refused error, not a raw 422", async () => {
    server.use(
      http.post(`${HTTP_BASE}/sessions`, () =>
        HttpResponse.json({ detail: "no such model: made-up" }, { status: 422 }),
      ),
    );

    const call = api().createSession("made-up", new AbortController().signal);
    await expect(call).rejects.toBeInstanceOf(MarketDataError);
    await expect(call).rejects.toMatchObject({ kind: "refused", message: "no such model: made-up" });
  });
});

describe("agentApi.setSessionModel", () => {
  it("PATCHes the session and returns it with the new model", async () => {
    let body: unknown;
    server.use(
      http.patch(`${HTTP_BASE}/sessions/7`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          id: 7,
          title: "why is BTC flat",
          current_model_id: "gpt-5.6-sol",
          created_at: "2026-08-11T10:00:00Z",
          last_active_at: "2026-08-11T10:05:00Z",
        });
      }),
    );

    const session = await api().setSessionModel(7, "gpt-5.6-sol", new AbortController().signal);
    expect(body).toEqual({ model_id: "gpt-5.6-sol" });
    expect(session.currentModelId).toBe("gpt-5.6-sol");
  });
});

describe("agentApi.getMessages", () => {
  it("maps a foreign or missing session to not-found", async () => {
    server.use(
      http.get(`${HTTP_BASE}/sessions/9/messages`, () =>
        HttpResponse.json({ detail: "no such session" }, { status: 404 }),
      ),
    );

    const call = api().getMessages(9, new AbortController().signal);
    await expect(call).rejects.toMatchObject({ kind: "not-found", message: "no such session" });
  });

  it("maps operator and agent turns, and passes incomplete through", async () => {
    server.use(
      http.get(`${HTTP_BASE}/sessions/7/messages`, () =>
        HttpResponse.json([
          {
            id: 1,
            role: "operator",
            content: "why is BTC flat",
            model_id: null,
            prompt_version: null,
            incomplete: false,
            created_at: "2026-08-11T10:00:00Z",
          },
          {
            id: 2,
            role: "agent",
            content: "consolidating near",
            model_id: "gpt-5.6-luna",
            prompt_version: "v1",
            incomplete: true,
            created_at: "2026-08-11T10:00:05Z",
          },
        ]),
      ),
    );

    const messages = await api().getMessages(7, new AbortController().signal);
    expect(messages).toEqual([
      {
        id: 1,
        role: "operator",
        content: "why is BTC flat",
        modelId: null,
        promptVersion: null,
        incomplete: false,
        // Neither `tool_calls` nor `stopped` is in this response at all, which is a module from before it
        // published either. Empty and false, not undefined — the panel maps over one and branches on the other.
        stopped: false,
        createdAt: 1786442400,
        toolCalls: [],
      },
      {
        id: 2,
        role: "agent",
        content: "consolidating near",
        modelId: "gpt-5.6-luna",
        promptVersion: "v1",
        incomplete: true,
        stopped: false,
        createdAt: 1786442405,
        toolCalls: [],
      },
    ]);
  });

  it("passes the module's own stopped mark through, beside incomplete", async () => {
    server.use(
      http.get(`${HTTP_BASE}/sessions/7/messages`, () =>
        HttpResponse.json([
          {
            id: 2,
            role: "agent",
            content: "half an ",
            model_id: "gpt-5.6-luna",
            prompt_version: "v1",
            incomplete: true,
            stopped: true,
            created_at: "2026-08-11T10:00:05Z",
            tool_calls: [],
          },
        ]),
      ),
    );

    const [reply] = await api().getMessages(7, new AbortController().signal);
    expect(reply.incomplete).toBe(true);
    expect(reply.stopped).toBe(true);
  });

  it("maps the tool calls a reply was reached through", async () => {
    server.use(
      http.get(`${HTTP_BASE}/sessions/7/messages`, () =>
        HttpResponse.json([
          {
            id: 2,
            role: "agent",
            content: "US100 is at 29698.2",
            model_id: "gpt-5.6-luna",
            prompt_version: "v3",
            incomplete: false,
            created_at: "2026-08-11T10:00:05Z",
            tool_calls: [
              {
                round_index: 0,
                position: 0,
                tool_name: "get_last_price",
                arguments: { symbol: "US100", resolution: "DAY" },
                outcome: "ok",
                result_text: '{"close": 29698.2}',
                duration_ms: 63,
                source: "server",
              },
              {
                round_index: 0,
                position: 1,
                tool_name: "describe_coverage",
                arguments: { symbol: "US100" },
                outcome: "refused",
                result_text: "market-data refused: no such pair",
                duration_ms: 18,
                source: "server",
              },
            ],
          },
        ]),
      ),
    );

    const [message] = await api().getMessages(7, new AbortController().signal);

    expect(message.toolCalls).toEqual([
      {
        roundIndex: 0,
        position: 0,
        name: "get_last_price",
        arguments: { symbol: "US100", resolution: "DAY" },
        outcome: "ok",
        resultText: '{"close": 29698.2}',
        durationMs: 63,
        source: "server",
      },
      {
        roundIndex: 0,
        position: 1,
        name: "describe_coverage",
        arguments: { symbol: "US100" },
        outcome: "refused",
        resultText: "market-data refused: no such pair",
        durationMs: 18,
        source: "server",
      },
    ]);
  });
});

describe("agentApi.sendMessage", () => {
  it("hands back the turn's events, parsed from the streamed body", async () => {
    server.use(
      http.post(`${HTTP_BASE}/sessions/7/messages`, () => {
        const body = new ReadableStream<Uint8Array>({
          start(controller) {
            const encoder = new TextEncoder();
            controller.enqueue(encoder.encode('event: fragment\ndata: {"text":"why is "}\n\n'));
            controller.enqueue(encoder.encode('event: fragment\ndata: {"text":"BTC flat"}\n\n'));
            controller.enqueue(encoder.encode('event: complete\ndata: {"incomplete":false}\n\n'));
            controller.close();
          },
        });
        return new Response(body, {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        });
      }),
    );

    const events = [];
    for await (const event of await api().sendMessage(7, "why is BTC flat", new AbortController().signal)) {
      events.push(event);
    }
    expect(events).toEqual([
      { kind: "fragment", text: "why is " },
      { kind: "fragment", text: "BTC flat" },
      { kind: "complete", incomplete: false },
    ]);
  });

  function emptyCompleteStream() {
    return new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('event: complete\ndata: {"incomplete":false}\n\n'));
        controller.close();
      },
    });
  }

  it("sends the visible span as ISO instants when both halves are known", async () => {
    let body: unknown;
    server.use(
      http.post(`${HTTP_BASE}/sessions/7/messages`, async ({ request }) => {
        body = await request.json();
        return new Response(emptyCompleteStream(), {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        });
      }),
    );

    await api().sendMessage(7, "what do you see", new AbortController().signal, {
      symbol: "US100",
      resolution: "MINUTE_5",
      indicators: [],
      visibleFrom: 1767398400,
      visibleTo: 1767484800,
    });

    expect(body).toEqual({
      content: "what do you see",
      chart: {
        symbol: "US100",
        resolution: "MINUTE_5",
        indicators: [],
        visible_from: "2026-01-03T00:00:00.000Z",
        visible_to: "2026-01-04T00:00:00.000Z",
      },
    });
  });

  it("sends neither half of the visible span when only one is known", async () => {
    let body: unknown;
    server.use(
      http.post(`${HTTP_BASE}/sessions/7/messages`, async ({ request }) => {
        body = await request.json();
        return new Response(emptyCompleteStream(), {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        });
      }),
    );

    await api().sendMessage(7, "what do you see", new AbortController().signal, {
      symbol: "US100",
      resolution: "MINUTE_5",
      indicators: [],
      visibleFrom: 1767398400,
      visibleTo: null,
    });

    expect(body).toEqual({
      content: "what do you see",
      chart: { symbol: "US100", resolution: "MINUTE_5", indicators: [] },
    });
  });

  it("rejects before yielding anything when the session is missing", async () => {
    server.use(
      http.post(`${HTTP_BASE}/sessions/9/messages`, () =>
        HttpResponse.json({ detail: "no such session" }, { status: 404 }),
      ),
    );

    await expect(
      api().sendMessage(9, "hello", new AbortController().signal),
    ).rejects.toMatchObject({ kind: "not-found" });
  });
});

describe("agentApi.usage", () => {
  it("sends the range as ISO instants and maps the summary, costs kept as strings", async () => {
    let asked: URL | null = null;
    server.use(
      http.get(`${HTTP_BASE}/usage`, ({ request }) => {
        asked = new URL(request.url);
        return HttpResponse.json({
          total_cost: "1.2345",
          by_model: [
            { key: "gpt-5.6-luna", input_tokens: 3000, output_tokens: 700, cost: "0.0026", unknown_count: 0 },
          ],
          by_session: [],
          by_day: [],
        });
      }),
    );

    const summary = await api().usage(
      { from: 1786435200, to: 1786521599 },
      new AbortController().signal,
    );

    expect(asked!.searchParams.get("from")).toBe(new Date(1786435200 * 1000).toISOString());
    expect(asked!.searchParams.get("to")).toBe(new Date(1786521599 * 1000).toISOString());
    expect(summary).toEqual({
      totalCost: "1.2345",
      byModel: [
        { key: "gpt-5.6-luna", inputTokens: 3000, outputTokens: 700, cost: "0.0026", unknownCount: 0 },
      ],
      bySession: [],
      byDay: [],
    });
  });

  it("sends no query at all for an unbounded range", async () => {
    let asked: URL | null = null;
    server.use(
      http.get(`${HTTP_BASE}/usage`, ({ request }) => {
        asked = new URL(request.url);
        return HttpResponse.json({ total_cost: "0", by_model: [], by_session: [], by_day: [] });
      }),
    );

    await api().usage({}, new AbortController().signal);
    expect(asked!.search).toBe("");
  });
});

describe("agentApi.chartCommand", () => {
  it("maps a null focus through untouched", async () => {
    server.use(
      http.get(`${HTTP_BASE}/chart`, () =>
        HttpResponse.json({
          sequence: 3,
          symbol: "US100",
          resolution: null,
          indicators: null,
          focus: null,
        }),
      ),
    );

    const command = await api().chartCommand(0, new AbortController().signal);
    expect(command?.focus).toBeNull();
  });

  it("maps a range focus from ISO instants to epoch seconds", async () => {
    server.use(
      http.get(`${HTTP_BASE}/chart`, () =>
        HttpResponse.json({
          sequence: 3,
          symbol: null,
          resolution: null,
          indicators: null,
          focus: {
            from: "2026-01-03T00:00:00Z",
            to: "2026-01-04T00:00:00Z",
            around: null,
            bars: null,
            last_bars: null,
          },
        }),
      ),
    );

    const command = await api().chartCommand(0, new AbortController().signal);
    expect(command?.focus).toEqual({
      from: 1767398400,
      to: 1767484800,
      around: null,
      bars: null,
      lastBars: null,
    });
  });

  it("maps a last-bars focus, its number kept as a number", async () => {
    server.use(
      http.get(`${HTTP_BASE}/chart`, () =>
        HttpResponse.json({
          sequence: 3,
          symbol: null,
          resolution: null,
          indicators: null,
          focus: { from: null, to: null, around: null, bars: null, last_bars: 100 },
        }),
      ),
    );

    const command = await api().chartCommand(0, new AbortController().signal);
    expect(command?.focus).toEqual({
      from: null,
      to: null,
      around: null,
      bars: null,
      lastBars: 100,
    });
  });
});

describe("agentApi.getPrompt", () => {
  it("maps the current revision, both variants and the version", async () => {
    server.use(
      http.get(`${HTTP_BASE}/prompt`, () =>
        HttpResponse.json({
          version: "v4",
          with_tools: "you have tools",
          without_tools: "you have none",
          updated_at: "2026-08-11T10:00:00Z",
        }),
      ),
    );

    const prompt = await api().getPrompt(new AbortController().signal);
    expect(prompt).toEqual({
      version: "v4",
      withTools: "you have tools",
      withoutTools: "you have none",
      updatedAt: 1786442400,
    });
  });
});

describe("agentApi.updatePrompt", () => {
  it("PUTs both variants and maps back the new revision", async () => {
    let body: unknown;
    server.use(
      http.put(`${HTTP_BASE}/prompt`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          version: "v5",
          with_tools: "edited with tools",
          without_tools: "edited without tools",
          updated_at: "2026-08-11T10:05:00Z",
        });
      }),
    );

    const prompt = await api().updatePrompt(
      "edited with tools",
      "edited without tools",
      new AbortController().signal,
    );
    expect(body).toEqual({ with_tools: "edited with tools", without_tools: "edited without tools" });
    expect(prompt.version).toBe("v5");
  });

  it("maps a blank variant to a refused error, not a raw 422", async () => {
    server.use(
      http.put(`${HTTP_BASE}/prompt`, () =>
        HttpResponse.json({ detail: "with_tools is blank" }, { status: 422 }),
      ),
    );

    const call = api().updatePrompt("   ", "fine", new AbortController().signal);
    await expect(call).rejects.toMatchObject({ kind: "refused", message: "with_tools is blank" });
  });
});

describe("agentApi drawings", () => {
  function raw(overrides: Record<string, unknown> = {}) {
    return {
      id: 7,
      symbol: "US100",
      geometry: { kind: "level", price: 21500, at: null },
      label: "weekly high",
      color: "--color-up",
      created_at: "2026-01-03T00:00:00Z",
      updated_at: "2026-01-03T00:00:00Z",
      ...overrides,
    };
  }

  it("maps a level, its moments as epoch seconds", async () => {
    server.use(
      http.get(`${HTTP_BASE}/drawings`, () =>
        HttpResponse.json([raw({ geometry: { kind: "level", price: 21500, at: "2026-01-03T09:00:00Z" } })]),
      ),
    );

    const drawings = await api().listDrawings("US100", new AbortController().signal);
    expect(drawings).toEqual([
      {
        id: 7,
        symbol: "US100",
        geometry: { kind: "level", price: 21500, at: 1767430800 },
        label: "weekly high",
        color: "--color-up",
        hidden: false,
        createdAt: 1767398400,
        updatedAt: 1767398400,
      },
    ]);
  });

  it("maps a zone, keeping `top` and `bottom` apart", async () => {
    server.use(
      http.get(`${HTTP_BASE}/drawings`, () =>
        HttpResponse.json([
          raw({ geometry: { kind: "zone", top: 21600, bottom: 21550, from: null, to: null } }),
        ]),
      ),
    );

    const [drawing] = await api().listDrawings("US100", new AbortController().signal);
    expect(drawing.geometry).toEqual({ kind: "zone", top: 21600, bottom: 21550, from: null, to: null });
  });

  it("maps a trend line's two points", async () => {
    server.use(
      http.get(`${HTTP_BASE}/drawings`, () =>
        HttpResponse.json([
          raw({
            geometry: {
              kind: "trendline",
              a: { time: "2026-01-03T00:00:00Z", price: 21000 },
              b: { time: "2026-01-04T00:00:00Z", price: 21400 },
            },
          }),
        ]),
      ),
    );

    const [drawing] = await api().listDrawings("US100", new AbortController().signal);
    expect(drawing.geometry).toEqual({
      kind: "trendline",
      a: { time: 1767398400, price: 21000 },
      b: { time: 1767484800, price: 21400 },
    });
  });

  it("skips a kind it has no shape for rather than dropping the whole read", async () => {
    // A module deployed ahead of this terminal may publish a fourth shape. The objects
    // this terminal *can* draw must survive it.
    server.use(
      http.get(`${HTTP_BASE}/drawings`, () =>
        HttpResponse.json([raw({ id: 8, geometry: { kind: "fibonacci", levels: [] } }), raw()]),
      ),
    );

    const drawings = await api().listDrawings("US100", new AbortController().signal);
    expect(drawings.map((drawing) => drawing.id)).toEqual([7]);
  });

  it("sends only the price roles the caller named, in the module's own names", async () => {
    let body: unknown;
    server.use(
      http.patch(`${HTTP_BASE}/drawings/7`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(raw());
      }),
    );

    await api().patchDrawing(7, { aPrice: 21000, label: "trend" }, new AbortController().signal);
    expect(body).toEqual({ a_price: 21000, label: "trend" });
  });

  it("turns a 404 on removal into a not-found error rather than a silent success", async () => {
    server.use(
      http.delete(`${HTTP_BASE}/drawings/7`, () =>
        HttpResponse.json({ detail: "no drawing #7" }, { status: 404 }),
      ),
    );

    await expect(api().deleteDrawing(7, new AbortController().signal)).rejects.toBeInstanceOf(
      MarketDataError,
    );
  });
});
