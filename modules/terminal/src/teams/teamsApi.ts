import { noIdentity, type Identity } from "../auth/identity";
import { resolveEndpoints } from "../data/config";
import type { components } from "../data/contract.teams.generated";
import { jsonClient } from "../data/http";
import { identity } from "../data/marketData";
import { parseIsoToEpochSeconds } from "../data/time";
import { MarketDataError } from "../data/types";
import {
  mapRecordedToolCall,
  mapRun,
  mapRunStep,
  readRunStream,
  type RecordedToolCall,
  type RunStreamEvent,
  type TeamRun,
  type TeamRunStep,
} from "./runs";

/**
 * The teams module's client, over types generated from its own OpenAPI document rather
 * than hand-written the way `agentApi.ts` is. The two modules differ in exactly the way
 * design.md says they do: the agent's wire is a handful of narrow DTOs, this one is
 * graphs, revisions and runs — wide enough that a renamed field would arrive as
 * `undefined` and show up as a blank node rather than as a compile error.
 *
 * Regenerate with `pnpm contract:generate`; `pnpm contract:check` fails on a stale file.
 *
 * The module's own spelling (snake_case, `from` on an edge) stays inside this file and in
 * `runs.ts`, which holds the same rule for the run half — a progress frame carries the
 * same facts as the JSON read beside it, so both go through one set of mappers. Every
 * other file in `src/teams/` speaks the camelCase shapes below — same rule as
 * `archive.ts` and `agentApi.ts`, and the reason a wire change lands in one place.
 */

type Wire = components["schemas"];

type RawTeam = Wire["TeamOut"];
type RawRevision = Wire["TeamRevisionOut"];
type RawDefinition = Wire["TeamDefinition"];
type RawAgent = Wire["AgentDefinition"];
type RawModel = Wire["ModelOut"];
type RawTool = Wire["ToolOut"];
type RawLayout = Wire["TeamLayoutOut"];
type RawRun = Wire["RunOut"];
type RawStep = Wire["RunStepOut"];
type RawToolCall = Wire["ToolCallOut"];

/** One entry of the catalogue — everything the list needs, and no definition: reading
 *  the list must not pull down every team's graph (specs/teams-catalogue). */
export interface TeamSummary {
  id: number;
  name: string;
  description: string;
  latestRevision: number;
  createdAt: number;
  updatedAt: number;
}

export interface TeamAgent {
  /** Stable inside one revision: what dependencies point at and what a run's steps are
   *  recorded under. Not a display label — renaming a role never changes it. */
  key: string;
  role: string;
  prompt: string;
  guidance: string;
  modelId: string;
  tools: string[];
}

/** One dependency, in the direction work flows: `to` waits for `from` and is shown what
 *  it produced (`teams-runs`, "Agent widzi wypowiedzi poprzedników"). `from` is a
 *  reserved word on the wire's own model too — the module spells it `from`, this side
 *  keeps the same name because it is not a keyword in an object literal. */
export interface TeamDependency {
  from: string;
  to: string;
}

/** Budgets a revision carries. Strings, like every cost the terminal touches: it renders
 *  them, it never adds them up. */
export interface TeamLimits {
  runLimit: string | null;
  dailyLimit: string | null;
}

export interface TeamDefinition {
  agents: TeamAgent[];
  dependencies: TeamDependency[];
  limits: TeamLimits;
}

/** Agent key → where the operator left it. Sparse on purpose: an agent this does not name
 *  is placed by `layout()` from the dependencies, which is also the whole picture for a
 *  team nobody has arranged yet (specs/terminal-teams, "Agent bez zapamiętanego miejsca").
 *  Not part of `TeamDefinition` — moving a node is not a revision. */
export type TeamLayout = Map<string, { x: number; y: number }>;

export interface TeamRevision {
  id: number;
  teamId: number;
  version: number;
  definition: TeamDefinition;
  createdAt: number;
}

export interface TeamsModel {
  id: string;
  displayName: string;
  costRank: number;
  inputRatePer1M: string;
  outputRatePer1M: string;
}

/** One tool the module's tool server announces. Name and description only: a definition
 *  points at a tool by name and carries nothing else about it, so a description that
 *  changes upstream needs no revision rewritten (specs/teams-tool-access, "Moduł nie
 *  trzyma kopii tego, co ogłasza serwer narzędzi"). */
export interface TeamsTool {
  name: string;
  description: string;
}

export interface TeamsApi {
  listModels(signal: AbortSignal): Promise<TeamsModel[]>;
  /** What the module's tool server announces right now. An empty list is a working
   *  answer — no tool server configured, or one announcing nothing — and the picker says
   *  so rather than offering names this terminal invented. */
  listTools(signal: AbortSignal): Promise<TeamsTool[]>;
  listTeams(signal: AbortSignal): Promise<TeamSummary[]>;
  createTeam(
    name: string,
    description: string,
    definition: TeamDefinition,
    signal: AbortSignal,
  ): Promise<TeamSummary>;
  getTeam(id: number, signal: AbortSignal): Promise<TeamSummary>;
  /** The revision the canvas opens on. A team always has one — it is written with the
   *  team itself — so this answering 404 means the team is gone or was never anyone's. */
  latestRevision(id: number, signal: AbortSignal): Promise<TeamRevision>;
  getRevision(id: number, version: number, signal: AbortSignal): Promise<TeamRevision>;
  /** The revision by its own id — what a run names, and therefore what a monitor draws.
   *  Asking for the team's latest instead would show a graph the run is not running. */
  revisionById(revisionId: number, signal: AbortSignal): Promise<TeamRevision>;
  /** Appends. Rejects with a `"refused"` `MarketDataError` carrying the module's own
   *  message — which names the agent or the dependency at fault, and is what
   *  `refusal.ts` reads to put it next to that node on the canvas. */
  saveRevision(
    id: number,
    definition: TeamDefinition,
    signal: AbortSignal,
  ): Promise<TeamRevision>;
  /** Retires a team from the catalogue. Its runs and revisions stay readable — this is
   *  not a delete, whatever the verb says. */
  archiveTeam(id: number, signal: AbortSignal): Promise<void>;

  /** Where the operator left each agent. A team nobody has arranged answers with an empty
   *  layout, which is not an error: the canvas then places every agent from the
   *  dependencies (specs/terminal-teams). */
  layout(id: number, signal: AbortSignal): Promise<TeamLayout>;
  /** Replaces the layout. Never a revision — a moved node changes where the team is
   *  drawn, not what it is. */
  saveLayout(id: number, layout: TeamLayout, signal: AbortSignal): Promise<void>;

  /** Starts a run of the team's latest revision and comes back at once with the run, not
   *  with its result: a team takes minutes. Rejects `"refused"` when the module will not
   *  start it — a model withdrawn since the revision was saved, a tool no longer
   *  announced, the team's daily budget already spent — carrying the module's sentence. */
  startRun(teamId: number, signal: AbortSignal): Promise<TeamRun>;
  /** Every run of this team, newest first, including runs of revisions since replaced. */
  listRuns(teamId: number, signal: AbortSignal): Promise<TeamRun[]>;
  getRun(runId: number, signal: AbortSignal): Promise<TeamRun>;
  runSteps(runId: number, signal: AbortSignal): Promise<TeamRunStep[]>;
  /** What the agents called, as recorded — each naming its step rather than its agent.
   *  `attachAgentKeys` in `runs.ts` is where the two become one shape. */
  runToolCalls(runId: number, signal: AbortSignal): Promise<RecordedToolCall[]>;
  /** Asks the run to stop. The module answers 202 with the run as it was when the
   *  interruption was accepted — the status is written by the run itself as it unwinds,
   *  and this view catches up through the stream. */
  cancelRun(runId: number, signal: AbortSignal): Promise<TeamRun>;
  /** Progress as it happens, beginning with a snapshot of where the run is now. Dropping
   *  the connection — closing the view, aborting the signal — unsubscribes and nothing
   *  else: the run does not know anyone was watching (specs/teams-runs). */
  watchRun(runId: number, signal: AbortSignal): Promise<AsyncGenerator<RunStreamEvent>>;
}

function mapTeam(raw: RawTeam): TeamSummary {
  return {
    id: raw.id,
    name: raw.name,
    description: raw.description,
    latestRevision: raw.latest_revision,
    createdAt: parseIsoToEpochSeconds(raw.created_at),
    updatedAt: parseIsoToEpochSeconds(raw.updated_at),
  };
}

function mapAgent(raw: RawAgent): TeamAgent {
  return {
    key: raw.key,
    role: raw.role,
    prompt: raw.prompt,
    guidance: raw.guidance,
    modelId: raw.model_id,
    // Optional on the wire (it has a default), always a list here: a picker mapping over
    // `undefined` is a blank panel rather than an agent with no tools.
    tools: raw.tools ?? [],
  };
}

function mapDefinition(raw: RawDefinition): TeamDefinition {
  return {
    agents: raw.agents.map(mapAgent),
    dependencies: (raw.edges ?? []).map((edge) => ({ from: edge.from, to: edge.to })),
    limits: {
      runLimit: raw.limits?.run_limit ?? null,
      dailyLimit: raw.limits?.daily_limit ?? null,
    },
  };
}

function definitionToWire(definition: TeamDefinition): RawDefinition {
  return {
    agents: definition.agents.map((agent) => ({
      key: agent.key,
      role: agent.role,
      prompt: agent.prompt,
      guidance: agent.guidance,
      model_id: agent.modelId,
      tools: agent.tools,
    })),
    edges: definition.dependencies.map((edge) => ({ from: edge.from, to: edge.to })),
    limits: {
      run_limit: definition.limits.runLimit,
      daily_limit: definition.limits.dailyLimit,
    },
  };
}

function mapRevision(raw: RawRevision): TeamRevision {
  return {
    id: raw.id,
    teamId: raw.team_id,
    version: raw.version,
    definition: mapDefinition(raw.definition),
    createdAt: parseIsoToEpochSeconds(raw.created_at),
  };
}

function mapModel(raw: RawModel): TeamsModel {
  return {
    id: raw.id,
    displayName: raw.display_name,
    costRank: raw.cost_rank,
    inputRatePer1M: raw.input_rate_per_1m,
    outputRatePer1M: raw.output_rate_per_1m,
  };
}

function mapStatus(status: number, detail: string): MarketDataError {
  if (status === 404) return new MarketDataError("not-found", detail);
  // The module understood the definition and declined it: a cycle, an agent wired to
  // nothing, a model outside its catalogue, a tool it does not announce. The message is
  // the operator's whole lead, so it travels intact.
  if (status === 422) return new MarketDataError("refused", detail);
  return new MarketDataError("unknown", detail);
}

export function createTeamsApi(httpBase: string, identity: Identity = noIdentity): TeamsApi {
  const http = jsonClient("teams", mapStatus, identity);

  return {
    async listModels(signal) {
      const raw = await http.json<RawModel[]>(`${httpBase}/models`, { signal });
      return raw.map(mapModel);
    },

    async listTools(signal) {
      try {
        const raw = await http.json<RawTool[]>(`${httpBase}/tools`, { signal });
        return raw.map((tool) => ({ name: tool.name, description: tool.description }));
      } catch (cause) {
        // A module deployed before this route existed answers 404 here, and that reads
        // as "nothing announced" rather than as a failure: the panel still edits the
        // rest of an agent, and an already-assigned tool keeps its name (specs/
        // teams-tool-access — the module's announcement is the only source there is,
        // and inventing one here is exactly what it forbids).
        //
        // A tool server that is configured and unreachable is *not* folded in here: the
        // module answers 503, that reaches the panel as "the tool list could not be
        // read", and it is a different sentence because it is a different fact.
        if (cause instanceof MarketDataError && cause.kind === "not-found") return [];
        throw cause;
      }
    },

    async listTeams(signal) {
      const raw = await http.json<RawTeam[]>(`${httpBase}/teams`, { signal });
      return raw.map(mapTeam);
    },

    async createTeam(name, description, definition, signal) {
      const raw = await http.json<RawTeam>(`${httpBase}/teams`, {
        method: "POST",
        body: { name, description, definition: definitionToWire(definition) },
        signal,
      });
      return mapTeam(raw);
    },

    async getTeam(id, signal) {
      const raw = await http.json<RawTeam>(`${httpBase}/teams/${id}`, { signal });
      return mapTeam(raw);
    },

    async latestRevision(id, signal) {
      const raw = await http.json<RawRevision>(`${httpBase}/teams/${id}/revisions/latest`, {
        signal,
      });
      return mapRevision(raw);
    },

    async getRevision(id, version, signal) {
      const raw = await http.json<RawRevision>(`${httpBase}/teams/${id}/revisions/${version}`, {
        signal,
      });
      return mapRevision(raw);
    },

    async saveRevision(id, definition, signal) {
      const raw = await http.json<RawRevision>(`${httpBase}/teams/${id}/revisions`, {
        method: "POST",
        body: { definition: definitionToWire(definition) },
        signal,
      });
      return mapRevision(raw);
    },

    async revisionById(revisionId, signal) {
      const raw = await http.json<RawRevision>(`${httpBase}/revisions/${revisionId}`, { signal });
      return mapRevision(raw);
    },

    async archiveTeam(id, signal) {
      await http.send(`${httpBase}/teams/${id}`, { method: "DELETE", signal });
    },

    async layout(id, signal) {
      const raw = await http.json<RawLayout>(`${httpBase}/teams/${id}/layout`, { signal });
      return new Map(raw.places.map((place) => [place.agent_key, { x: place.x, y: place.y }]));
    },

    async saveLayout(id, layout, signal) {
      await http.send(`${httpBase}/teams/${id}/layout`, {
        method: "PUT",
        body: {
          places: [...layout].map(([agentKey, at]) => ({ agent_key: agentKey, x: at.x, y: at.y })),
        },
        signal,
      });
    },

    async startRun(teamId, signal) {
      const raw = await http.json<RawRun>(`${httpBase}/teams/${teamId}/runs`, {
        method: "POST",
        signal,
      });
      return mapRun(raw);
    },

    async listRuns(teamId, signal) {
      const raw = await http.json<RawRun[]>(`${httpBase}/teams/${teamId}/runs`, { signal });
      return raw.map(mapRun);
    },

    async getRun(runId, signal) {
      return mapRun(await http.json<RawRun>(`${httpBase}/runs/${runId}`, { signal }));
    },

    async runSteps(runId, signal) {
      const raw = await http.json<RawStep[]>(`${httpBase}/runs/${runId}/steps`, { signal });
      return raw.map(mapRunStep);
    },

    async runToolCalls(runId, signal) {
      const raw = await http.json<RawToolCall[]>(`${httpBase}/runs/${runId}/tool-calls`, {
        signal,
      });
      return raw.map(mapRecordedToolCall);
    },

    async cancelRun(runId, signal) {
      const raw = await http.json<RawRun>(`${httpBase}/runs/${runId}/cancel`, {
        method: "POST",
        signal,
      });
      return mapRun(raw);
    },

    async watchRun(runId, signal) {
      const response = await http.send(`${httpBase}/runs/${runId}/events`, { signal });
      if (response.body === null) {
        throw new MarketDataError("unknown", "teams sent no progress stream");
      }
      return readRunStream(response.body);
    },
  };
}

/** The one teams client the tab uses, sharing `identity` with every other module's —
 *  same operator, one sign-in. */
export const teamsApi: TeamsApi = createTeamsApi(resolveEndpoints().teamsHttp, identity);
