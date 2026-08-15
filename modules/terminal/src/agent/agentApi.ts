import { noIdentity, type Identity } from "../auth/identity";
import { resolveEndpoints } from "../data/config";
import { jsonClient } from "../data/http";
import { identity } from "../data/marketData";
import { parseIsoToEpochSeconds } from "../data/time";
import { MarketDataError } from "../data/types";
import { readAgentStream, type AgentStreamEvent } from "./stream";
import { mapToolCall, type AgentToolCall, type RawToolCall } from "./toolCall";

export type { AgentToolCall, ToolOutcome } from "./toolCall";

/**
 * The agent module's own DTOs, written by hand against its OpenAPI rather than
 * generated: `pnpm contract:generate` is wired to `market-data`'s one contract alone,
 * and giving the agent a second generator is a change of its own weight
 * (design.md, "Kontrakt terminala pisany ręcznie, bez generatora"; `modules/agent/
 * README.md`, "Contract"). The module's wire shapes (snake_case, per `agent/
 * contract.py`) stay private to this file — every other file speaks the camelCase
 * ones below.
 *
 * Money and rates travel as strings on the wire (`agent/contract.py`: "nothing here
 * ever sums these on the wire") and stay strings here too — this file renders them,
 * it does not add them (`terminal-agent-cost` spec, "Terminal MUST NOT liczyć kosztu").
 */

export interface AgentModel {
  id: string;
  displayName: string;
  costRank: number;
  inputRatePer1M: string;
  outputRatePer1M: string;
}

export type ChatRole = "operator" | "agent";

export interface AgentSession {
  id: number;
  title: string | null;
  currentModelId: string;
  createdAt: number;
  lastActiveAt: number;
}

export interface AgentMessage {
  id: number;
  role: ChatRole;
  content: string;
  modelId: string | null;
  promptVersion: string | null;
  incomplete: boolean;
  createdAt: number;
  /** How the agent got to this reply. Empty on an operator's message and on a reply that
   *  asked nothing — and empty, too, against a module from before `tool_calls` existed on
   *  the wire, which is the one case worth naming: the mapper defaults rather than reads
   *  `undefined.map`. */
  toolCalls: AgentToolCall[];
}

export interface AgentUsageAggregate {
  key: string;
  inputTokens: number;
  outputTokens: number;
  cost: string;
  unknownCount: number;
}

export interface AgentUsageSummary {
  totalCost: string;
  byModel: AgentUsageAggregate[];
  bySession: AgentUsageAggregate[];
  byDay: AgentUsageAggregate[];
}

export interface AgentPrompt {
  version: string;
  withTools: string;
  withoutTools: string;
  updatedAt: number;
}

export interface UsageRange {
  /** Epoch seconds, inclusive — converted to the ISO instants `GET /usage`'s `from`/`to`
   *  query params expect. Absent means "no bound on this side". */
  from?: number;
  to?: number;
}

/** One indicator the agent asked the chart to draw — the terminal's own selection shape
 *  minus the instance key, which this side hands out when it applies the command. */
export interface AgentChartIndicator {
  id: string;
  params: Record<string, number>;
  color: string | null;
}

/** What the agent set the chart to, as of `sequence`. A null field means "leave it as it
 *  is": several commands arrive folded into one, and a field none of them touched is
 *  still untouched here. */
export interface AgentChartCommand {
  sequence: number;
  symbol: string | null;
  resolution: string | null;
  indicators: AgentChartIndicator[] | null;
}

/** What the terminal is drawing as it asks — context for one turn, never a message. */
export interface AgentChartSnapshot {
  symbol: string | null;
  resolution: string;
  indicators: Array<{ id: string; params: Record<string, number>; color: string | null }>;
}

export interface AgentApi {
  listModels(signal: AbortSignal): Promise<AgentModel[]>;
  listSessions(signal: AbortSignal): Promise<AgentSession[]>;
  getSession(id: number, signal: AbortSignal): Promise<AgentSession>;
  createSession(modelId: string | null, signal: AbortSignal): Promise<AgentSession>;
  setSessionModel(id: number, modelId: string, signal: AbortSignal): Promise<AgentSession>;
  renameSession(id: number, title: string, signal: AbortSignal): Promise<AgentSession>;
  /** Resolves on 204 and rejects on anything else — there is no body to map. A session
   *  already gone answers 404, indistinguishable from one that never existed. */
  deleteSession(id: number, signal: AbortSignal): Promise<void>;
  getMessages(id: number, signal: AbortSignal): Promise<AgentMessage[]>;
  /** Posts the operator's turn and hands back its reply as typed events — the raw
   *  `fetch`/`ReadableStream` plumbing lives entirely in `stream.ts` and in the one
   *  await below. Rejecting here (before any event is produced) means nothing was
   *  accepted by the module; a rejection while iterating the result means the turn was
   *  accepted and broke partway through — `agentChatStore` tells the two apart, because
   *  only it knows what, if anything, is worth keeping on screen for each. */
  sendMessage(
    id: number,
    content: string,
    signal: AbortSignal,
    chart?: AgentChartSnapshot | null,
  ): Promise<AsyncGenerator<AgentStreamEvent>>;
  /** What the agent set the chart to since `after`, or null when it set nothing. Safe to
   *  repeat: the module keeps no cursor of its own, so asking twice answers twice the
   *  same (specs/agent-chart-control, "Konsument czyta tylko to, czego jeszcze nie
   *  zastosował"). */
  chartCommand(after: number, signal: AbortSignal): Promise<AgentChartCommand | null>;
  usage(range: UsageRange, signal: AbortSignal): Promise<AgentUsageSummary>;
  getPrompt(signal: AbortSignal): Promise<AgentPrompt>;
  /** Rejects with a `"refused"` `MarketDataError` on a blank variant — the module's own
   *  422, not a check this file makes first. */
  updatePrompt(withTools: string, withoutTools: string, signal: AbortSignal): Promise<AgentPrompt>;
}

interface RawModel {
  id: string;
  display_name: string;
  cost_rank: number;
  input_rate_per_1m: string;
  output_rate_per_1m: string;
}

interface RawSession {
  id: number;
  title: string | null;
  current_model_id: string;
  created_at: string;
  last_active_at: string;
}

interface RawMessage {
  id: number;
  role: string;
  content: string;
  model_id: string | null;
  prompt_version: string | null;
  incomplete: boolean;
  created_at: string;
  /** Optional here and required on the module's own contract: a terminal deployed ahead
   *  of the agent reads a transcript without it, and the panel must open rather than
   *  throw (design.md, "Agent sprzed zmiany wobec terminala po zmianie"). */
  tool_calls?: RawToolCall[];
}

interface RawChartCommand {
  sequence: number;
  symbol: string | null;
  resolution: string | null;
  indicators: Array<{ id: string; params: Record<string, number>; color: string | null }> | null;
}

function mapChartCommand(raw: RawChartCommand): AgentChartCommand {
  return {
    sequence: raw.sequence,
    symbol: raw.symbol,
    resolution: raw.resolution,
    indicators:
      raw.indicators === null
        ? null
        : raw.indicators.map((indicator) => ({
            id: indicator.id,
            params: indicator.params,
            color: indicator.color,
          })),
  };
}

interface RawUsageAggregate {
  key: string;
  input_tokens: number;
  output_tokens: number;
  cost: string;
  unknown_count: number;
}

interface RawUsageSummary {
  total_cost: string;
  by_model: RawUsageAggregate[];
  by_session: RawUsageAggregate[];
  by_day: RawUsageAggregate[];
}

interface RawPrompt {
  version: string;
  with_tools: string;
  without_tools: string;
  updated_at: string;
}

function mapModel(raw: RawModel): AgentModel {
  return {
    id: raw.id,
    displayName: raw.display_name,
    costRank: raw.cost_rank,
    inputRatePer1M: raw.input_rate_per_1m,
    outputRatePer1M: raw.output_rate_per_1m,
  };
}

function mapSession(raw: RawSession): AgentSession {
  return {
    id: raw.id,
    title: raw.title,
    currentModelId: raw.current_model_id,
    createdAt: parseIsoToEpochSeconds(raw.created_at),
    lastActiveAt: parseIsoToEpochSeconds(raw.last_active_at),
  };
}

function mapMessage(raw: RawMessage): AgentMessage {
  return {
    id: raw.id,
    role: raw.role === "operator" ? "operator" : "agent",
    content: raw.content,
    modelId: raw.model_id,
    promptVersion: raw.prompt_version,
    incomplete: raw.incomplete,
    createdAt: parseIsoToEpochSeconds(raw.created_at),
    toolCalls: (raw.tool_calls ?? []).map(mapToolCall),
  };
}

function mapUsageAggregate(raw: RawUsageAggregate): AgentUsageAggregate {
  return {
    key: raw.key,
    inputTokens: raw.input_tokens,
    outputTokens: raw.output_tokens,
    cost: raw.cost,
    unknownCount: raw.unknown_count,
  };
}

function mapUsageSummary(raw: RawUsageSummary): AgentUsageSummary {
  return {
    totalCost: raw.total_cost,
    byModel: raw.by_model.map(mapUsageAggregate),
    bySession: raw.by_session.map(mapUsageAggregate),
    byDay: raw.by_day.map(mapUsageAggregate),
  };
}

function mapPrompt(raw: RawPrompt): AgentPrompt {
  return {
    version: raw.version,
    withTools: raw.with_tools,
    withoutTools: raw.without_tools,
    updatedAt: parseIsoToEpochSeconds(raw.updated_at),
  };
}

function mapStatus(status: number, detail: string): MarketDataError {
  if (status === 404) return new MarketDataError("not-found", detail);
  // A model id the catalogue does not know, or a patch with none at all — the module
  // understood the request and declined it, same as a resolution the archive will not
  // take on.
  if (status === 422) return new MarketDataError("refused", detail);
  return new MarketDataError("unknown", detail);
}

export function createAgentApi(httpBase: string, identity: Identity = noIdentity): AgentApi {
  const http = jsonClient("agent", mapStatus, identity);

  return {
    async listModels(signal) {
      const raw = await http.json<RawModel[]>(`${httpBase}/models`, { signal });
      return raw.map(mapModel);
    },

    async listSessions(signal) {
      const raw = await http.json<RawSession[]>(`${httpBase}/sessions`, { signal });
      return raw.map(mapSession);
    },

    async getSession(id, signal) {
      const raw = await http.json<RawSession>(`${httpBase}/sessions/${id}`, { signal });
      return mapSession(raw);
    },

    async createSession(modelId, signal) {
      const raw = await http.json<RawSession>(`${httpBase}/sessions`, {
        method: "POST",
        body: { model_id: modelId },
        signal,
      });
      return mapSession(raw);
    },

    async setSessionModel(id, modelId, signal) {
      const raw = await http.json<RawSession>(`${httpBase}/sessions/${id}`, {
        method: "PATCH",
        body: { model_id: modelId },
        signal,
      });
      return mapSession(raw);
    },

    async renameSession(id, title, signal) {
      const raw = await http.json<RawSession>(`${httpBase}/sessions/${id}`, {
        method: "PATCH",
        body: { title },
        signal,
      });
      return mapSession(raw);
    },

    async deleteSession(id, signal) {
      await http.send(`${httpBase}/sessions/${id}`, { method: "DELETE", signal });
    },

    async getMessages(id, signal) {
      const raw = await http.json<RawMessage[]>(`${httpBase}/sessions/${id}/messages`, { signal });
      return raw.map(mapMessage);
    },

    async sendMessage(id, content, signal, chart = null) {
      const response = await http.send(`${httpBase}/sessions/${id}/messages`, {
        method: "POST",
        body: chart === null ? { content } : { content, chart },
        signal,
      });
      if (response.body === null) {
        throw new MarketDataError("unknown", "agent sent no stream body");
      }
      return readAgentStream(response.body);
    },

    async chartCommand(after, signal) {
      const raw = await http.json<RawChartCommand | null>(
        `${httpBase}/chart?after=${after}`,
        { signal },
      );
      return raw === null ? null : mapChartCommand(raw);
    },

    async usage(range, signal) {
      const params = new URLSearchParams();
      if (range.from !== undefined) params.set("from", new Date(range.from * 1000).toISOString());
      if (range.to !== undefined) params.set("to", new Date(range.to * 1000).toISOString());
      const query = params.toString();
      const raw = await http.json<RawUsageSummary>(
        `${httpBase}/usage${query ? `?${query}` : ""}`,
        { signal },
      );
      return mapUsageSummary(raw);
    },

    async getPrompt(signal) {
      const raw = await http.json<RawPrompt>(`${httpBase}/prompt`, { signal });
      return mapPrompt(raw);
    },

    async updatePrompt(withTools, withoutTools, signal) {
      const raw = await http.json<RawPrompt>(`${httpBase}/prompt`, {
        method: "PUT",
        body: { with_tools: withTools, without_tools: withoutTools },
        signal,
      });
      return mapPrompt(raw);
    },
  };
}

/**
 * The one agent client the panel and the cost tab both use. Shares `identity` with
 * `marketData.ts` rather than minting a second one — same operator, same Entra
 * registration's worth of session state, and a second `MSAL` instance would just be two
 * copies of the same sign-in.
 */
export const agentApi: AgentApi = createAgentApi(resolveEndpoints().agentHttp, identity);
