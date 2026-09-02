/**
 * The workbench's conversation, over types generated from its own OpenAPI document
 * (`contract.agent.generated.ts`) — since P8 on this side and the terminal's alike. The `map*` functions
 * stay hand-written: they turn ISO strings into dates and snake into camel.
 *
 * **The browser never speaks MCP.** The tools this screen shows running are the workbench's: it holds
 * the model key and the tool servers' addresses, and `polymarket-data`'s tool surface admits its
 * managed identity and nobody else's.
 */

import { noIdentity, type Identity } from "../auth/identity";
import type { components } from "../data/contract.agent.generated";
import { jsonClient, type FailureKind } from "../data/http";
import { readAgentStream, type AgentStreamEvent } from "./stream";
import { mapToolCall, type AgentToolCall } from "./toolCall";

export type { AgentToolCall, ToolOutcome } from "./toolCall";
export type { AgentStreamEvent } from "./stream";

export type ChatRole = "operator" | "agent";

export interface AgentModel {
  id: string;
  displayName: string;
  costRank: number;
}

export interface AgentSession {
  id: number;
  title: string | null;
  currentModelId: string;
  lastActiveAt: Date;
}

export interface AgentMessage {
  id: number;
  role: ChatRole;
  content: string;
  /** The turn ended without finishing. `stopped` says the operator ended it, which is the difference
   *  between "it broke" and "I stopped it" — a distinction the screen must not blur. */
  incomplete: boolean;
  stopped: boolean;
  createdAt: Date;
  /** How the agent got to this reply. Empty on an operator's message and on a reply that asked
   *  nothing; optional on the wire, so a screen deployed ahead of the module still opens. */
  toolCalls: AgentToolCall[];
}

type Wire = components["schemas"];
type RawModel = Wire["ModelOut"];
type RawSession = Wire["SessionOut"];
// `stopped` and `tool_calls` are required on the wire and still read with a fallback below: a screen
// deployed ahead of the module reads a transcript without them, and it must open rather than throw.
type RawMessage = Wire["MessageOut"];

function mapSession(raw: RawSession): AgentSession {
  return {
    id: raw.id,
    title: raw.title,
    currentModelId: raw.current_model_id,
    lastActiveAt: new Date(raw.last_active_at),
  };
}

function mapMessage(raw: RawMessage): AgentMessage {
  return {
    id: raw.id,
    // Anything the module has that this build does not know is the agent talking: an operator's
    // message is the one this screen wrote itself.
    role: raw.role === "operator" ? "operator" : "agent",
    content: raw.content,
    incomplete: raw.incomplete,
    stopped: raw.stopped ?? false,
    createdAt: new Date(raw.created_at),
    toolCalls: (raw.tool_calls ?? []).map(mapToolCall),
  };
}

/** 403 is a refusal of the caller, not a sign-in problem: the gate authorizes an application. 402 is
 *  the cost limit, which is the workbench saying no rather than failing. */
const STATUS_KINDS: Partial<Record<number, FailureKind>> = {
  402: "refused",
  403: "refused",
  404: "not-found",
  409: "refused",
  422: "refused",
  502: "upstream",
};

export interface AgentApi {
  listModels(signal: AbortSignal): Promise<AgentModel[]>;
  listSessions(signal: AbortSignal): Promise<AgentSession[]>;
  createSession(modelId: string | null, signal: AbortSignal): Promise<AgentSession>;
  setModel(sessionId: number, modelId: string, signal: AbortSignal): Promise<AgentSession>;
  listMessages(sessionId: number, signal: AbortSignal): Promise<AgentMessage[]>;
  /** The turn as it happens. The operator's own message is already stored by the time the first
   *  fragment arrives — the module writes it before the model is ever called. */
  sendMessage(
    sessionId: number,
    content: string,
    signal: AbortSignal,
  ): Promise<AsyncGenerator<AgentStreamEvent>>;
  /** Ends the running turn. What was said stays: the partial reply comes back from the transcript
   *  marked stopped, not discarded. */
  stop(sessionId: number, signal: AbortSignal): Promise<void>;
}

export function createAgentApi(base: string, identity: Identity = noIdentity): AgentApi {
  const http = jsonClient("workbench", STATUS_KINDS, identity);

  return {
    async listModels(signal) {
      const raw = await http.json<RawModel[]>(`${base}/models`, { signal });
      return raw.map((model) => ({
        id: model.id,
        displayName: model.display_name,
        costRank: model.cost_rank,
      }));
    },

    async listSessions(signal) {
      const raw = await http.json<RawSession[]>(`${base}/sessions`, { signal });
      return raw.map(mapSession);
    },

    async createSession(modelId, signal) {
      const raw = await http.json<RawSession>(`${base}/sessions`, {
        signal,
        method: "POST",
        // Omitted rather than null when there is none: the module has a default model of its own,
        // and a null would be this screen choosing to have no model.
        body: modelId === null ? {} : { model_id: modelId },
      });
      return mapSession(raw);
    },

    async setModel(sessionId, modelId, signal) {
      const raw = await http.json<RawSession>(`${base}/sessions/${sessionId}`, {
        signal,
        method: "PATCH",
        body: { model_id: modelId },
      });
      return mapSession(raw);
    },

    async listMessages(sessionId, signal) {
      const raw = await http.json<RawMessage[]>(`${base}/sessions/${sessionId}/messages`, {
        signal,
      });
      return raw.map(mapMessage);
    },

    async sendMessage(sessionId, content, signal) {
      const response = await http.send(`${base}/sessions/${sessionId}/messages`, {
        signal,
        method: "POST",
        body: { content },
      });
      if (response.body === null) {
        throw new Error("the workbench answered the turn with no body to read");
      }
      return readAgentStream(response.body);
    },

    async stop(sessionId, signal) {
      await http.send(`${base}/sessions/${sessionId}/stop`, { signal, method: "POST" });
    },
  };
}
