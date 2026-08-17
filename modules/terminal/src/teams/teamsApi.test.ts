import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { MarketDataError } from "../data/types";
import { http, HttpResponse, setupServer } from "../test/httpDouble";
import { createTeamsApi, type TeamDefinition } from "./teamsApi";

const HTTP_BASE = "http://teams.test";

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function api() {
  return createTeamsApi(HTTP_BASE);
}

const wireRevision = {
  id: 3,
  team_id: 1,
  version: 2,
  created_at: "2026-08-16T10:00:00Z",
  definition: {
    agents: [
      {
        key: "agent-1",
        role: "Scout",
        prompt: "look",
        guidance: "",
        model_id: "a-model",
        tools: ["get_candles"],
      },
      { key: "agent-2", role: "Judge", prompt: "weigh", guidance: "", model_id: "a-model" },
    ],
    edges: [{ from: "agent-1", to: "agent-2" }],
    limits: { run_limit: "0.5", daily_limit: null },
    trading: { max_order_size: "2", orders_per_run: 3, orders_per_day: null },
  },
};

const definition: TeamDefinition = {
  agents: [
    {
      key: "agent-1",
      role: "Scout",
      prompt: "look",
      guidance: "",
      modelId: "a-model",
      tools: ["get_candles"],
    },
    { key: "agent-2", role: "Judge", prompt: "weigh", guidance: "", modelId: "a-model", tools: [] },
  ],
  dependencies: [{ from: "agent-1", to: "agent-2" }],
  limits: { runLimit: "0.5", dailyLimit: null },
  trading: { maxOrderSize: "2", ordersPerRun: 3, ordersPerDay: null },
};

describe("listTeams", () => {
  it("maps the catalogue, ISO instants to epoch seconds", async () => {
    server.use(
      http.get(`${HTTP_BASE}/teams`, () =>
        HttpResponse.json([
          {
            id: 1,
            name: "Morning desk",
            description: "two roles",
            latest_revision: 2,
            created_at: "2026-08-15T08:00:00Z",
            updated_at: "2026-08-16T09:30:00Z",
          },
        ]),
      ),
    );

    expect(await api().listTeams(new AbortController().signal)).toEqual([
      {
        id: 1,
        name: "Morning desk",
        description: "two roles",
        latestRevision: 2,
        createdAt: Date.parse("2026-08-15T08:00:00Z") / 1000,
        updatedAt: Date.parse("2026-08-16T09:30:00Z") / 1000,
      },
    ]);
  });
});

describe("a revision, both ways", () => {
  it("maps a definition off the wire, an absent tools list becoming an empty one", async () => {
    server.use(http.get(`${HTTP_BASE}/teams/1/revisions/latest`, () => HttpResponse.json(wireRevision)));

    const revision = await api().latestRevision(1, new AbortController().signal);

    expect(revision.version).toBe(2);
    expect(revision.definition).toEqual(definition);
  });

  it("sends it back in the module's own spelling, `from` included", async () => {
    let body: unknown;
    server.use(
      http.post(`${HTTP_BASE}/teams/1/revisions`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(wireRevision, { status: 201 });
      }),
    );

    await api().saveRevision(1, definition, new AbortController().signal);

    expect(body).toEqual({
      definition: {
        agents: [
          {
            key: "agent-1",
            role: "Scout",
            prompt: "look",
            guidance: "",
            model_id: "a-model",
            tools: ["get_candles"],
          },
          {
            key: "agent-2",
            role: "Judge",
            prompt: "weigh",
            guidance: "",
            model_id: "a-model",
            tools: [],
          },
        ],
        edges: [{ from: "agent-1", to: "agent-2" }],
        limits: { run_limit: "0.5", daily_limit: null },
        trading: { max_order_size: "2", orders_per_run: 3, orders_per_day: null },
      },
    });
  });

  it("carries the module's refusal message through untouched", async () => {
    // It names the agent or the dependency at fault, and that is the operator's whole
    // lead — `refusal.ts` reads it back out to put it on the canvas.
    server.use(
      http.post(`${HTTP_BASE}/teams/1/revisions`, () =>
        HttpResponse.json(
          { detail: "agent 'agent-2' names model 'gone', which is not in this module's catalogue" },
          { status: 422 },
        ),
      ),
    );

    await expect(api().saveRevision(1, definition, new AbortController().signal)).rejects.toThrow(
      /agent-2/,
    );
    await expect(
      api().saveRevision(1, definition, new AbortController().signal),
    ).rejects.toMatchObject({ kind: "refused" });
  });
});

describe("createTeam", () => {
  it("posts name, description and definition together", async () => {
    let body: unknown;
    server.use(
      http.post(`${HTTP_BASE}/teams`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(
          {
            id: 4,
            name: "Morning desk",
            description: "two roles",
            latest_revision: 1,
            created_at: "2026-08-16T09:00:00Z",
            updated_at: "2026-08-16T09:00:00Z",
          },
          { status: 201 },
        );
      }),
    );

    const team = await api().createTeam(
      "Morning desk",
      "two roles",
      definition,
      new AbortController().signal,
    );

    expect(team.id).toBe(4);
    expect(body).toMatchObject({ name: "Morning desk", description: "two roles" });
  });
});

describe("archiveTeam", () => {
  it("resolves on 204 and refuses a team that is not there", async () => {
    server.use(http.delete(`${HTTP_BASE}/teams/1`, () => new Response(null, { status: 204 })));
    await expect(api().archiveTeam(1, new AbortController().signal)).resolves.toBeUndefined();

    server.resetHandlers();
    server.use(
      http.delete(`${HTTP_BASE}/teams/2`, () =>
        HttpResponse.json({ detail: "no such team" }, { status: 404 }),
      ),
    );
    await expect(api().archiveTeam(2, new AbortController().signal)).rejects.toBeInstanceOf(
      MarketDataError,
    );
  });
});

describe("the layout", () => {
  it("reads the module's places into a map keyed by agent", async () => {
    server.use(
      http.get(`${HTTP_BASE}/teams/1/layout`, () =>
        HttpResponse.json({
          places: [
            { agent_key: "agent-1", x: -120.5, y: 40 },
            { agent_key: "agent-2", x: 320, y: 40 },
          ],
        }),
      ),
    );

    const layout = await api().layout(1, new AbortController().signal);

    expect(layout.get("agent-1")).toEqual({ x: -120.5, y: 40 });
    expect(layout.get("agent-2")).toEqual({ x: 320, y: 40 });
  });

  it("reads a team nobody has arranged as an empty map, not as a missing one", async () => {
    server.use(http.get(`${HTTP_BASE}/teams/1/layout`, () => HttpResponse.json({ places: [] })));

    expect((await api().layout(1, new AbortController().signal)).size).toBe(0);
  });

  it("sends the whole arrangement back in the module's own spelling", async () => {
    let sent: unknown = null;
    server.use(
      http.put(`${HTTP_BASE}/teams/1/layout`, async ({ request }) => {
        sent = await request.json();
        return HttpResponse.json({ places: [] });
      }),
    );

    await api().saveLayout(
      1,
      new Map([["agent-1", { x: 10, y: 20 }]]),
      new AbortController().signal,
    );

    expect(sent).toEqual({ places: [{ agent_key: "agent-1", x: 10, y: 20 }] });
  });
});

describe("listTools", () => {
  it("reads what the module announces, including which tools move the account", async () => {
    server.use(
      http.get(`${HTTP_BASE}/tools`, () =>
        HttpResponse.json([
          { name: "get_candles", description: "candles", read_only: true },
          { name: "place_order", description: "an order", read_only: false },
        ]),
      ),
    );

    expect(await api().listTools(new AbortController().signal)).toEqual([
      { name: "get_candles", description: "candles", readOnly: true },
      { name: "place_order", description: "an order", readOnly: false },
    ]);
  });

  it("keeps an unannotated tool unannotated rather than calling it read-only", async () => {
    // specs/trading-mcp-tools over this side of the wire: `null` is a third value. A tool
    // nobody annotated is one nobody said anything about, and promoting it to "reads
    // only" here would be this terminal holding an opinion about somebody else's tool.
    server.use(
      http.get(`${HTTP_BASE}/tools`, () =>
        HttpResponse.json([{ name: "get_candles", description: "candles" }]),
      ),
    );

    expect(await api().listTools(new AbortController().signal)).toEqual([
      { name: "get_candles", description: "candles", readOnly: null },
    ]);
  });

  it("reads a module without that route as announcing nothing", async () => {
    // A terminal deployed ahead of the module: the panel still edits an agent's role and
    // model, and no tool name is invented here to fill the gap.
    server.use(
      http.get(`${HTTP_BASE}/tools`, () =>
        HttpResponse.json({ detail: "Not Found" }, { status: 404 }),
      ),
    );

    expect(await api().listTools(new AbortController().signal)).toEqual([]);
  });

  it("does not read an unreachable tool server as an empty catalogue", async () => {
    // 503 is the module saying it could not ask — a different fact from "nothing is
    // announced", and one the panel says in its own words rather than hiding.
    server.use(
      http.get(`${HTTP_BASE}/tools`, () =>
        HttpResponse.json({ detail: "the tool server did not answer" }, { status: 503 }),
      ),
    );

    await expect(api().listTools(new AbortController().signal)).rejects.toBeInstanceOf(
      MarketDataError,
    );
  });
});

const wireRun = {
  id: 7,
  team_revision_id: 3,
  status: "running",
  stopped_reason: null,
  started_at: "2026-08-16T10:00:05Z",
  finished_at: null,
  created_at: "2026-08-16T10:00:00Z",
};

describe("runs", () => {
  it("starts one on the team and maps what comes back", async () => {
    server.use(
      http.post(`${HTTP_BASE}/teams/1/runs`, () => HttpResponse.json(wireRun, { status: 201 })),
    );

    expect(await api().startRun(1, new AbortController().signal)).toEqual({
      id: 7,
      teamRevisionId: 3,
      status: "running",
      stoppedReason: null,
      startedAt: Date.parse("2026-08-16T10:00:05Z") / 1000,
      finishedAt: null,
      createdAt: Date.parse("2026-08-16T10:00:00Z") / 1000,
    });
  });

  it("carries a refusal to start through as the module wrote it", async () => {
    server.use(
      http.post(`${HTTP_BASE}/teams/1/runs`, () =>
        HttpResponse.json(
          { detail: "the team spent 4.20 of its daily 4.00" },
          { status: 422 },
        ),
      ),
    );

    await expect(api().startRun(1, new AbortController().signal)).rejects.toMatchObject({
      kind: "refused",
      message: "the team spent 4.20 of its daily 4.00",
    });
  });

  it("reads the revision a run names, by its id", async () => {
    server.use(http.get(`${HTTP_BASE}/revisions/3`, () => HttpResponse.json(wireRevision)));

    const revision = await api().revisionById(3, new AbortController().signal);

    expect(revision.version).toBe(2);
    expect(revision.definition).toEqual(definition);
  });

  it("reads the progress stream as the events it carries", async () => {
    server.use(
      http.get(`${HTTP_BASE}/runs/7/events`, () =>
        new HttpResponse(
          `event: snapshot\ndata: ${JSON.stringify({ run: wireRun, steps: [] })}\n\n` +
            ': ping\n\nevent: step_started\ndata: {"agent_key":"agent-1"}\n\n',
          { headers: { "Content-Type": "text/event-stream" } },
        ),
      ),
    );

    const seen = [];
    for await (const event of await api().watchRun(7, new AbortController().signal)) {
      seen.push(event);
    }

    // The keepalive between them is not an event, and the snapshot arrives mapped.
    expect(seen).toEqual([
      { kind: "snapshot", run: expect.objectContaining({ id: 7 }), steps: [] },
      { kind: "stepStarted", agentKey: "agent-1" },
    ]);
  });

  it("reads what the run did to the account, each row naming its own agent", async () => {
    server.use(
      http.get(`${HTTP_BASE}/runs/7/trades`, () =>
        HttpResponse.json([
          {
            id: 4,
            run_id: 7,
            run_step_id: 2,
            agent_key: "agent-2",
            tool_name: "place_order",
            symbol: "US100",
            direction: "BUY",
            size: "1.5",
            level: null,
            status: "settled",
            result_status: "FILLED",
            provider_order_id: "o-1",
            reference: "r-1",
            created_at: "2026-08-16T10:01:00Z",
            settled_at: "2026-08-16T10:01:02Z",
          },
        ]),
      ),
    );

    expect(await api().runTrades(7, new AbortController().signal)).toEqual([
      {
        id: 4,
        runId: 7,
        agentKey: "agent-2",
        toolName: "place_order",
        symbol: "US100",
        direction: "BUY",
        size: "1.5",
        level: null,
        status: "settled",
        resultStatus: "FILLED",
        providerOrderId: "o-1",
        reference: "r-1",
        createdAt: Date.parse("2026-08-16T10:01:00Z") / 1000,
        settledAt: Date.parse("2026-08-16T10:01:02Z") / 1000,
      },
    ]);
  });
});

const wireSchedule = {
  id: 11,
  team_id: 1,
  revision_mode: "pinned",
  pinned_revision_id: 3,
  cron_expression: "*/5 * * * *",
  recurrence: {
    kind: "every_minutes",
    minutes: 5,
    minute: null,
    hour: null,
    weekdays: null,
    day_of_month: null,
  },
  next_fire_at: "2026-08-16T20:05:00Z",
  enabled: true,
  disabled_reason: null,
  consecutive_failures: 0,
  created_at: "2026-08-16T09:00:00Z",
  updated_at: "2026-08-16T09:00:00Z",
};

describe("schedules", () => {
  it("maps the wire shape, ISO instants to epoch seconds", async () => {
    server.use(http.get(`${HTTP_BASE}/teams/1/schedules`, () => HttpResponse.json([wireSchedule])));

    expect(await api().listSchedules(1, new AbortController().signal)).toEqual([
      {
        id: 11,
        teamId: 1,
        revisionMode: "pinned",
        pinnedRevisionId: 3,
        cronExpression: "*/5 * * * *",
        recurrence: {
          kind: "every_minutes",
          minutes: 5,
          minute: null,
          hour: null,
          weekdays: null,
          dayOfMonth: null,
        },
        nextFireAt: Date.parse("2026-08-16T20:05:00Z") / 1000,
        enabled: true,
        disabledReason: null,
        consecutiveFailures: 0,
        createdAt: Date.parse("2026-08-16T09:00:00Z") / 1000,
        updatedAt: Date.parse("2026-08-16T09:00:00Z") / 1000,
      },
    ]);
  });

  it("posts a draft in the module's own spelling", async () => {
    let body: unknown;
    server.use(
      http.post(`${HTTP_BASE}/teams/1/schedules`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(wireSchedule, { status: 201 });
      }),
    );

    await api().createSchedule(
      1,
      {
        revisionMode: "pinned",
        pinnedRevisionId: 3,
        cronExpression: "*/5 * * * *",
        recurrence: null,
      },
      new AbortController().signal,
    );

    expect(body).toEqual({
      revision_mode: "pinned",
      pinned_revision_id: 3,
      cron_expression: "*/5 * * * *",
      recurrence: null,
    });
  });

  it("posts a rhythm in the module's own spelling, snake_case and all", async () => {
    let body: unknown;
    server.use(
      http.post(`${HTTP_BASE}/teams/1/schedules`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(wireSchedule, { status: 201 });
      }),
    );

    await api().createSchedule(
      1,
      {
        revisionMode: "pinned",
        pinnedRevisionId: 3,
        cronExpression: null,
        recurrence: {
          kind: "weekly",
          minutes: null,
          minute: 30,
          hour: 8,
          weekdays: [1, 5],
          dayOfMonth: null,
        },
      },
      new AbortController().signal,
    );

    expect(body).toEqual({
      revision_mode: "pinned",
      pinned_revision_id: 3,
      cron_expression: null,
      recurrence: {
        kind: "weekly",
        minutes: null,
        minute: 30,
        hour: 8,
        weekdays: [1, 5],
        day_of_month: null,
      },
    });
  });

  it("previews a draft's next fires without saving it", async () => {
    let body: unknown;
    server.use(
      http.post(`${HTTP_BASE}/schedules/next-fires`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ times: ["2026-08-17T07:00:00Z", "2026-08-18T07:00:00Z"] });
      }),
    );

    const times = await api().previewNextFires(
      {
        cronExpression: null,
        recurrence: {
          kind: "daily",
          minutes: null,
          minute: 0,
          hour: 9,
          weekdays: null,
          dayOfMonth: null,
        },
      },
      2,
      new AbortController().signal,
    );

    expect(times).toEqual([
      Date.parse("2026-08-17T07:00:00Z") / 1000,
      Date.parse("2026-08-18T07:00:00Z") / 1000,
    ]);
    expect(body).toMatchObject({ count: 2, recurrence: { kind: "daily", hour: 9 } });
  });

  it("carries a refusal through as the module wrote it", async () => {
    server.use(
      http.post(`${HTTP_BASE}/teams/1/schedules`, () =>
        HttpResponse.json({ detail: "not a valid five-field cron expression" }, { status: 422 }),
      ),
    );

    await expect(
      api().createSchedule(
        1,
        {
          revisionMode: "pinned",
          pinnedRevisionId: 3,
          cronExpression: "not a cron",
          recurrence: null,
        },
        new AbortController().signal,
      ),
    ).rejects.toMatchObject({ kind: "refused", message: "not a valid five-field cron expression" });
  });

  it("enables and disables by id", async () => {
    server.use(
      http.post(`${HTTP_BASE}/schedules/11/disable`, () =>
        HttpResponse.json({ ...wireSchedule, enabled: false }),
      ),
    );
    expect((await api().disableSchedule(11, new AbortController().signal)).enabled).toBe(false);

    server.resetHandlers();
    server.use(
      http.post(`${HTTP_BASE}/schedules/11/enable`, () => HttpResponse.json(wireSchedule)),
    );
    expect((await api().enableSchedule(11, new AbortController().signal)).enabled).toBe(true);
  });

  it("reads fire history, including a fire that started nothing", async () => {
    server.use(
      http.get(`${HTTP_BASE}/schedules/11/fires`, () =>
        HttpResponse.json([
          {
            id: 1,
            schedule_id: 11,
            trigger_id: null,
            fired_at: "2026-08-16T20:00:00Z",
            outcome: "skipped",
            reason: "the previous run of this schedule is still working",
            run_id: null,
            skipped_count: 0,
          },
        ]),
      ),
    );

    const fires = await api().scheduleFires(11, new AbortController().signal);

    expect(fires).toEqual([
      {
        id: 1,
        scheduleId: 11,
        triggerId: null,
        firedAt: Date.parse("2026-08-16T20:00:00Z") / 1000,
        outcome: "skipped",
        reason: "the previous run of this schedule is still working",
        runId: null,
        skippedCount: 0,
      },
    ]);
  });

  it("asks for the next fires by count and maps them to epoch seconds", async () => {
    let query: string | null = null;
    server.use(
      http.get(`${HTTP_BASE}/schedules/11/next-fires`, ({ request }) => {
        query = new URL(request.url).searchParams.get("count");
        return HttpResponse.json({ times: ["2026-08-16T20:05:00Z", "2026-08-16T20:10:00Z"] });
      }),
    );

    const times = await api().nextFires(11, 2, new AbortController().signal);

    expect(query).toBe("2");
    expect(times).toEqual([Date.parse("2026-08-16T20:05:00Z") / 1000, Date.parse("2026-08-16T20:10:00Z") / 1000]);
  });
});

const wireTrigger = {
  id: 21,
  team_id: 1,
  revision_mode: "latest",
  pinned_revision_id: null,
  tool_name: "read_indicators",
  arguments: { symbol: "US100" },
  field_path: "rsi",
  comparison: "gt",
  threshold: "70.00000000",
  cooldown_seconds: 900,
  poll_interval_seconds: 300,
  next_check_at: "2026-08-16T20:00:00Z",
  last_result: null,
  last_checked_at: null,
  last_fired_at: null,
  enabled: true,
  disabled_reason: null,
  consecutive_failures: 0,
  created_at: "2026-08-16T09:00:00Z",
  updated_at: "2026-08-16T09:00:00Z",
};

describe("triggers", () => {
  it("maps the wire shape, including a lastResult that has never been checked", async () => {
    server.use(http.get(`${HTTP_BASE}/teams/1/triggers`, () => HttpResponse.json([wireTrigger])));

    const triggers = await api().listTriggers(1, new AbortController().signal);

    expect(triggers).toEqual([
      {
        id: 21,
        teamId: 1,
        revisionMode: "latest",
        pinnedRevisionId: null,
        toolName: "read_indicators",
        arguments: { symbol: "US100" },
        fieldPath: "rsi",
        comparison: "gt",
        threshold: "70.00000000",
        cooldownSeconds: 900,
        pollIntervalSeconds: 300,
        nextCheckAt: Date.parse("2026-08-16T20:00:00Z") / 1000,
        lastResult: null,
        lastCheckedAt: null,
        lastFiredAt: null,
        enabled: true,
        disabledReason: null,
        consecutiveFailures: 0,
        createdAt: Date.parse("2026-08-16T09:00:00Z") / 1000,
        updatedAt: Date.parse("2026-08-16T09:00:00Z") / 1000,
      },
    ]);
  });

  it("posts a draft in the module's own spelling", async () => {
    let body: unknown;
    server.use(
      http.post(`${HTTP_BASE}/teams/1/triggers`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(wireTrigger, { status: 201 });
      }),
    );

    await api().createTrigger(
      1,
      {
        revisionMode: "latest",
        pinnedRevisionId: null,
        toolName: "read_indicators",
        arguments: { symbol: "US100" },
        fieldPath: "rsi",
        comparison: "gt",
        threshold: "70",
        cooldownSeconds: 900,
        pollIntervalSeconds: 300,
      },
      new AbortController().signal,
    );

    expect(body).toEqual({
      revision_mode: "latest",
      pinned_revision_id: null,
      tool_name: "read_indicators",
      arguments: { symbol: "US100" },
      field_path: "rsi",
      comparison: "gt",
      threshold: "70",
      cooldown_seconds: 900,
      poll_interval_seconds: 300,
    });
  });

  it("reads fire history, distinguishing unavailable from a started run", async () => {
    server.use(
      http.get(`${HTTP_BASE}/triggers/21/fires`, () =>
        HttpResponse.json([
          {
            id: 2,
            schedule_id: null,
            trigger_id: 21,
            fired_at: "2026-08-16T20:00:00Z",
            outcome: "unavailable",
            reason: "no tool server is configured (MARKET_MCP_URL is unset)",
            run_id: null,
            skipped_count: 0,
          },
        ]),
      ),
    );

    const fires = await api().triggerFires(21, new AbortController().signal);

    expect(fires[0]).toMatchObject({ outcome: "unavailable", runId: null });
  });
});
