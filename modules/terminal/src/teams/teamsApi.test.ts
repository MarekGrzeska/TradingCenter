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

describe("listTools", () => {
  it("reads what the module announces", async () => {
    server.use(
      http.get(`${HTTP_BASE}/tools`, () =>
        HttpResponse.json([{ name: "get_candles", description: "candles" }]),
      ),
    );

    expect(await api().listTools(new AbortController().signal)).toEqual([
      { name: "get_candles", description: "candles" },
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
});
