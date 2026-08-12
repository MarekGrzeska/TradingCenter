import { noIdentity, type Identity } from "../auth/identity";
import { resolveEndpoints } from "../data/config";
import { jsonClient } from "../data/http";
import { identity } from "../data/marketData";
import { parseIsoToEpochSeconds } from "../data/time";
import { MarketDataError } from "../data/types";
import { readAgentStream, type AgentStreamEvent } from "./stream";

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

export interface UsageRange {
  /** Epoch seconds, inclusive — converted to the ISO instants `GET /usage`'s `from`/`to`
   *  query params expect. Absent means "no bound on this side". */
  from?: number;
  to?: number;
}

export interface AgentApi {
  listModels(signal: AbortSignal): Promise<AgentModel[]>;
  listSessions(signal: AbortSignal): Promise<AgentSession[]>;
  getSession(id: number, signal: AbortSignal): Promise<AgentSession>;
  createSession(modelId: string | null, signal: AbortSignal): Promise<AgentSession>;
  setSessionModel(id: number, modelId: string, signal: AbortSignal): Promise<AgentSession>;
  getMessages(id: number, signal: AbortSignal): Promise<AgentMessage[]>;
  /** Posts the operator's turn and hands back its reply as typed events — the raw
   *  `fetch`/`ReadableStream` plumbing lives entirely in `stream.ts` and in the one
   *  await below. Rejecting here (before any event is produced) means nothing was
   *  accepted by the module; a rejection while iterating the result means the turn was
   *  accepted and broke partway through — `agentChatStore` tells the two apart, because
   *  only it knows what, if anything, is worth keeping on screen for each. */
  sendMessage(id: number, content: string, signal: AbortSignal): Promise<AsyncGenerator<AgentStreamEvent>>;
  usage(range: UsageRange, signal: AbortSignal): Promise<AgentUsageSummary>;
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

    async getMessages(id, signal) {
      const raw = await http.json<RawMessage[]>(`${httpBase}/sessions/${id}/messages`, { signal });
      return raw.map(mapMessage);
    },

    async sendMessage(id, content, signal) {
      const response = await http.send(`${httpBase}/sessions/${id}/messages`, {
        method: "POST",
        body: { content },
        signal,
      });
      if (response.body === null) {
        throw new MarketDataError("unknown", "agent sent no stream body");
      }
      return readAgentStream(response.body);
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
  };
}

/**
 * The one agent client the panel and the cost tab both use. Shares `identity` with
 * `marketData.ts` rather than minting a second one — same operator, same Entra
 * registration's worth of session state, and a second `MSAL` instance would just be two
 * copies of the same sign-in.
 */
export const agentApi: AgentApi = createAgentApi(resolveEndpoints().agentHttp, identity);
