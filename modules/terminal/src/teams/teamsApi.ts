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
type RawSchedule = Wire["ScheduleOut"];
type RawScheduleIn = Wire["ScheduleIn"];
type RawTrigger = Wire["TriggerOut"];
type RawTriggerIn = Wire["TriggerIn"];
type RawFire = Wire["ScheduleFireOut"];
type RawNextFires = Wire["NextFiresOut"];

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

/** `pinned` names a revision, `latest` follows whatever the team's newest one is at the
 *  moment of each fire — an explicit choice, never the default (specs/teams-schedules,
 *  "tryb «najnowsza» jest jawnym wyborem"). */
export type RevisionMode = "pinned" | "latest";

export type TriggerComparison = "gt" | "gte" | "lt" | "lte" | "eq";

/** A team's own clock. Every field the module keeps, including the ones this terminal
 *  only displays — `nextFireAt` chiefly, which the module computes and this side never
 *  recomputes (`terminal-teams-schedules`, "Terminal nie liczy czasu wyzwolenia sam"). */
export interface Schedule {
  id: number;
  teamId: number;
  revisionMode: RevisionMode;
  pinnedRevisionId: number | null;
  cronExpression: string;
  nextFireAt: number;
  enabled: boolean;
  disabledReason: string | null;
  consecutiveFailures: number;
  unattendedAck: boolean;
  createdAt: number;
  updatedAt: number;
}

/** What an operator submits to create or edit a schedule — everything `Schedule` carries
 *  except what only the module ever writes (`id`, `nextFireAt`, `enabled`, the failure
 *  streak). */
export interface ScheduleDraft {
  revisionMode: RevisionMode;
  pinnedRevisionId: number | null;
  cronExpression: string;
  unattendedAck: boolean;
}

/** A market condition, expressed as a call to a tool this module already reads through —
 *  never a locally computed indicator (specs/teams-triggers, "Warunek jest czytany
 *  narzędziami serwera narzędzi"). `lastResult` is `null` until the first check, and
 *  `null` again whenever the tool server could not be asked — a third value, not a
 *  `false` (specs/teams-triggers, "Niedostępność serwera narzędzi to nie jest
 *  niespełniony warunek"). */
export interface Trigger {
  id: number;
  teamId: number;
  revisionMode: RevisionMode;
  pinnedRevisionId: number | null;
  toolName: string;
  arguments: Record<string, unknown>;
  fieldPath: string;
  comparison: TriggerComparison;
  threshold: string;
  cooldownSeconds: number;
  pollIntervalSeconds: number;
  nextCheckAt: number;
  lastResult: boolean | null;
  lastCheckedAt: number | null;
  lastFiredAt: number | null;
  enabled: boolean;
  disabledReason: string | null;
  consecutiveFailures: number;
  unattendedAck: boolean;
  createdAt: number;
  updatedAt: number;
}

export interface TriggerDraft {
  revisionMode: RevisionMode;
  pinnedRevisionId: number | null;
  toolName: string;
  arguments: Record<string, unknown>;
  fieldPath: string;
  comparison: TriggerComparison;
  threshold: string;
  cooldownSeconds: number;
  pollIntervalSeconds: number;
  unattendedAck: boolean;
}

/** One fire attempt from a schedule or a trigger — including one that started nothing.
 *  Exactly one of `scheduleId`/`triggerId` is set (specs/teams-schedules, "Wyzwolenie
 *  bez przebiegu zostawia zapisany powód"). */
export interface ScheduleFire {
  id: number;
  scheduleId: number | null;
  triggerId: number | null;
  firedAt: number;
  outcome: string;
  reason: string | null;
  runId: number | null;
  skippedCount: number;
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

  /** A team's schedules — its own clock, not a run's. */
  listSchedules(teamId: number, signal: AbortSignal): Promise<Schedule[]>;
  /** Rejects `"refused"` when the pinned or latest revision cannot be run unattended —
   *  a model outside the catalogue, or a state-changing tool with no acknowledgement. */
  createSchedule(teamId: number, draft: ScheduleDraft, signal: AbortSignal): Promise<Schedule>;
  updateSchedule(id: number, draft: ScheduleDraft, signal: AbortSignal): Promise<Schedule>;
  enableSchedule(id: number, signal: AbortSignal): Promise<Schedule>;
  disableSchedule(id: number, signal: AbortSignal): Promise<Schedule>;
  /** Every fire this schedule has had, newest first — including ones that started
   *  nothing (`terminal-teams-schedules`, "Historia pokazuje także to, co się nie
   *  wydarzyło"). */
  scheduleFires(id: number, signal: AbortSignal): Promise<ScheduleFire[]>;
  /** The module's own answer to "when does this fire next" — never computed here
   *  (`terminal-teams-schedules`, "Terminal nie liczy czasu wyzwolenia sam"). */
  nextFires(id: number, count: number, signal: AbortSignal): Promise<number[]>;

  listTriggers(teamId: number, signal: AbortSignal): Promise<Trigger[]>;
  createTrigger(teamId: number, draft: TriggerDraft, signal: AbortSignal): Promise<Trigger>;
  updateTrigger(id: number, draft: TriggerDraft, signal: AbortSignal): Promise<Trigger>;
  enableTrigger(id: number, signal: AbortSignal): Promise<Trigger>;
  disableTrigger(id: number, signal: AbortSignal): Promise<Trigger>;
  triggerFires(id: number, signal: AbortSignal): Promise<ScheduleFire[]>;
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

function mapSchedule(raw: RawSchedule): Schedule {
  return {
    id: raw.id,
    teamId: raw.team_id,
    revisionMode: raw.revision_mode as RevisionMode,
    pinnedRevisionId: raw.pinned_revision_id,
    cronExpression: raw.cron_expression,
    nextFireAt: parseIsoToEpochSeconds(raw.next_fire_at),
    enabled: raw.enabled,
    disabledReason: raw.disabled_reason,
    consecutiveFailures: raw.consecutive_failures,
    unattendedAck: raw.unattended_ack,
    createdAt: parseIsoToEpochSeconds(raw.created_at),
    updatedAt: parseIsoToEpochSeconds(raw.updated_at),
  };
}

function scheduleDraftToWire(draft: ScheduleDraft): RawScheduleIn {
  return {
    revision_mode: draft.revisionMode,
    pinned_revision_id: draft.pinnedRevisionId,
    cron_expression: draft.cronExpression,
    unattended_ack: draft.unattendedAck,
  };
}

function mapTrigger(raw: RawTrigger): Trigger {
  return {
    id: raw.id,
    teamId: raw.team_id,
    revisionMode: raw.revision_mode as RevisionMode,
    pinnedRevisionId: raw.pinned_revision_id,
    toolName: raw.tool_name,
    arguments: raw.arguments,
    fieldPath: raw.field_path,
    comparison: raw.comparison as TriggerComparison,
    threshold: raw.threshold,
    cooldownSeconds: raw.cooldown_seconds,
    pollIntervalSeconds: raw.poll_interval_seconds,
    nextCheckAt: parseIsoToEpochSeconds(raw.next_check_at),
    lastResult: raw.last_result,
    lastCheckedAt: raw.last_checked_at === null ? null : parseIsoToEpochSeconds(raw.last_checked_at),
    lastFiredAt: raw.last_fired_at === null ? null : parseIsoToEpochSeconds(raw.last_fired_at),
    enabled: raw.enabled,
    disabledReason: raw.disabled_reason,
    consecutiveFailures: raw.consecutive_failures,
    unattendedAck: raw.unattended_ack,
    createdAt: parseIsoToEpochSeconds(raw.created_at),
    updatedAt: parseIsoToEpochSeconds(raw.updated_at),
  };
}

function triggerDraftToWire(draft: TriggerDraft): RawTriggerIn {
  return {
    revision_mode: draft.revisionMode,
    pinned_revision_id: draft.pinnedRevisionId,
    tool_name: draft.toolName,
    arguments: draft.arguments,
    field_path: draft.fieldPath,
    comparison: draft.comparison,
    threshold: draft.threshold,
    cooldown_seconds: draft.cooldownSeconds,
    poll_interval_seconds: draft.pollIntervalSeconds,
    unattended_ack: draft.unattendedAck,
  };
}

function mapFire(raw: RawFire): ScheduleFire {
  return {
    id: raw.id,
    scheduleId: raw.schedule_id,
    triggerId: raw.trigger_id,
    firedAt: parseIsoToEpochSeconds(raw.fired_at),
    outcome: raw.outcome,
    reason: raw.reason,
    runId: raw.run_id,
    skippedCount: raw.skipped_count,
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

    async listSchedules(teamId, signal) {
      const raw = await http.json<RawSchedule[]>(`${httpBase}/teams/${teamId}/schedules`, {
        signal,
      });
      return raw.map(mapSchedule);
    },

    async createSchedule(teamId, draft, signal) {
      const raw = await http.json<RawSchedule>(`${httpBase}/teams/${teamId}/schedules`, {
        method: "POST",
        body: scheduleDraftToWire(draft),
        signal,
      });
      return mapSchedule(raw);
    },

    async updateSchedule(id, draft, signal) {
      const raw = await http.json<RawSchedule>(`${httpBase}/schedules/${id}`, {
        method: "PUT",
        body: scheduleDraftToWire(draft),
        signal,
      });
      return mapSchedule(raw);
    },

    async enableSchedule(id, signal) {
      const raw = await http.json<RawSchedule>(`${httpBase}/schedules/${id}/enable`, {
        method: "POST",
        signal,
      });
      return mapSchedule(raw);
    },

    async disableSchedule(id, signal) {
      const raw = await http.json<RawSchedule>(`${httpBase}/schedules/${id}/disable`, {
        method: "POST",
        signal,
      });
      return mapSchedule(raw);
    },

    async scheduleFires(id, signal) {
      const raw = await http.json<RawFire[]>(`${httpBase}/schedules/${id}/fires`, { signal });
      return raw.map(mapFire);
    },

    async nextFires(id, count, signal) {
      const raw = await http.json<RawNextFires>(
        `${httpBase}/schedules/${id}/next-fires?count=${count}`,
        { signal },
      );
      return raw.times.map(parseIsoToEpochSeconds);
    },

    async listTriggers(teamId, signal) {
      const raw = await http.json<RawTrigger[]>(`${httpBase}/teams/${teamId}/triggers`, {
        signal,
      });
      return raw.map(mapTrigger);
    },

    async createTrigger(teamId, draft, signal) {
      const raw = await http.json<RawTrigger>(`${httpBase}/teams/${teamId}/triggers`, {
        method: "POST",
        body: triggerDraftToWire(draft),
        signal,
      });
      return mapTrigger(raw);
    },

    async updateTrigger(id, draft, signal) {
      const raw = await http.json<RawTrigger>(`${httpBase}/triggers/${id}`, {
        method: "PUT",
        body: triggerDraftToWire(draft),
        signal,
      });
      return mapTrigger(raw);
    },

    async enableTrigger(id, signal) {
      const raw = await http.json<RawTrigger>(`${httpBase}/triggers/${id}/enable`, {
        method: "POST",
        signal,
      });
      return mapTrigger(raw);
    },

    async disableTrigger(id, signal) {
      const raw = await http.json<RawTrigger>(`${httpBase}/triggers/${id}/disable`, {
        method: "POST",
        signal,
      });
      return mapTrigger(raw);
    },

    async triggerFires(id, signal) {
      const raw = await http.json<RawFire[]>(`${httpBase}/triggers/${id}/fires`, { signal });
      return raw.map(mapFire);
    },
  };
}

/** The one teams client the tab uses, sharing `identity` with every other module's —
 *  same operator, one sign-in. */
export const teamsApi: TeamsApi = createTeamsApi(resolveEndpoints().teamsHttp, identity);
