import { noIdentity, type Identity } from "../auth/identity";
import { resolveEndpoints } from "../data/config";
import { jsonClient, statusMapper } from "../data/http";
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

/** Which fragment of the time axis the chart should show — epoch seconds here, ISO 8601
 *  UTC on the wire (`parseIsoToEpochSeconds`, the same conversion every other timestamp
 *  from this module goes through). Exactly one of the three shapes is filled: a
 *  `from`/`to` range, an `around`/`bars` point, or `lastBars` alone. */
export interface AgentChartFocus {
  from: number | null;
  to: number | null;
  around: number | null;
  bars: number | null;
  lastBars: number | null;
}

/** What the agent set the chart to, as of `sequence`. A null field means "leave it as it
 *  is": several commands arrive folded into one, and a field none of them touched is
 *  still untouched here. */
export interface AgentChartCommand {
  sequence: number;
  symbol: string | null;
  resolution: string | null;
  indicators: AgentChartIndicator[] | null;
  focus: AgentChartFocus | null;
}

/** One object standing on an instrument's chart, in the terminal's own shapes: epoch
 *  seconds for every moment, and the geometry a union discriminated by `kind` exactly as
 *  the module publishes it (`agent-chart-drawings` spec, "Rysunek należy do instrumentu,
 *  nie do widoku").
 *
 *  Unlike an indicator result, this is not computed from candles and does not belong to
 *  the interval it was made on — it belongs to the instrument, and the chart keeps it
 *  across a resolution change. */
export type AgentDrawingGeometry =
  | { kind: "level"; price: number; at: number | null }
  | { kind: "zone"; top: number; bottom: number; from: number | null; to: number | null }
  | {
      kind: "trendline";
      a: { time: number; price: number };
      b: { time: number; price: number };
    };

export interface AgentChartDrawing {
  id: number;
  symbol: string;
  geometry: AgentDrawingGeometry;
  label: string | null;
  color: string | null;
  /** Whether the chart draws it. Hidden is not removed: the object keeps everything else
   *  it has and comes back exactly as it was (`agent-chart-drawings` spec, "Zapalony
   *  rysunek jest tym samym rysunkiem"). */
  hidden: boolean;
  createdAt: number;
  updatedAt: number;
}

/** What the operator may correct by hand. Every field optional and at least one required
 *  — the module's own 422 says so, this side does not check first. The price fields are
 *  named by the role they play in a shape, and only the ones that shape has are accepted
 *  (`agent/contract.py`, `PatchDrawingIn`). */
export interface AgentDrawingPatch {
  price?: number;
  top?: number;
  bottom?: number;
  aPrice?: number;
  bPrice?: number;
  label?: string;
  /** Hiding travels this route rather than one of its own: it is a correction of the
   *  drawing like any other, and an absent field keeps meaning "leave it". */
  hidden?: boolean;
}

/** What the terminal is drawing as it asks — context for one turn, never a message.
 *  `visibleFrom`/`visibleTo` (epoch seconds) are the visible span, both present or both
 *  absent: half a span is not a span, and the module reads exactly that distinction to
 *  decide whether to say anything about it at all. */
export interface AgentChartSnapshot {
  symbol: string | null;
  resolution: string;
  indicators: Array<{ id: string; params: Record<string, number>; color: string | null }>;
  visibleFrom?: number | null;
  visibleTo?: number | null;
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
  /** The calls this conversation made that no reply ever claimed — a turn that died with
   *  something in flight (`agent-trading` spec). Empty for almost every conversation, and
   *  a row here is the record of an order whose fate nobody knows, so it is read and shown
   *  rather than left in the database.
   *
   *  Its own route rather than a field on the transcript: that one publishes a list, and a
   *  field would have meant an object, which a terminal deployed before the module would
   *  have called `map` on. */
  getUnclaimedToolCalls(id: number, signal: AbortSignal): Promise<AgentToolCall[]>;
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
  /** Everything drawn on this instrument, read whole. No cursor and nothing folded: a
   *  drawing is the instrument's state, not a log to catch up with, so the answer
   *  replaces what the chart shows rather than adding to it (design.md of
   *  `agent-chart-drawings`, "Rysunek jest stanem, nie logiem"). */
  listDrawings(symbol: string, signal: AbortSignal): Promise<AgentChartDrawing[]>;
  /** Rejects with a `"refused"` `MarketDataError` on a price role this shape does not
   *  have, or a zone whose band would end up inverted — the module's own 422. */
  patchDrawing(
    id: number,
    patch: AgentDrawingPatch,
    signal: AbortSignal,
  ): Promise<AgentChartDrawing>;
  /** Resolves on 204. A drawing already gone answers 404 — a `"not-found"` error rather
   *  than a quiet success, which is what lets the list say the removal did not happen
   *  (`terminal-chart` spec, "Usunięcie się nie powiodło"). */
  deleteDrawing(id: number, signal: AbortSignal): Promise<void>;
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

interface RawChartFocus {
  from: string | null;
  to: string | null;
  around: string | null;
  bars: number | null;
  last_bars: number | null;
}

interface RawChartCommand {
  sequence: number;
  symbol: string | null;
  resolution: string | null;
  indicators: Array<{ id: string; params: Record<string, number>; color: string | null }> | null;
  focus: RawChartFocus | null;
}

function mapChartFocus(raw: RawChartFocus): AgentChartFocus {
  return {
    from: raw.from === null ? null : parseIsoToEpochSeconds(raw.from),
    to: raw.to === null ? null : parseIsoToEpochSeconds(raw.to),
    around: raw.around === null ? null : parseIsoToEpochSeconds(raw.around),
    bars: raw.bars,
    lastBars: raw.last_bars,
  };
}

interface WireChartSnapshot {
  symbol: string | null;
  resolution: string;
  indicators: Array<{ id: string; params: Record<string, number>; color: string | null }>;
  visible_from?: string;
  visible_to?: string;
}

/** The one place `AgentChartSnapshot` meets the wire — `sendMessage`'s `chart` field is
 *  otherwise passed through untouched, which only ever worked because `symbol`,
 *  `resolution` and `indicators` happen to spell the same both ways. The visible span
 *  does not: epoch seconds here, an ISO instant there, and included only when both
 *  halves are known — an ISO instant invented for the half that is not would be a kadr
 *  the module was never actually shown. */
function chartSnapshotToWire(snapshot: AgentChartSnapshot): WireChartSnapshot {
  const wire: WireChartSnapshot = {
    symbol: snapshot.symbol,
    resolution: snapshot.resolution,
    indicators: snapshot.indicators,
  };
  if (snapshot.visibleFrom != null && snapshot.visibleTo != null) {
    wire.visible_from = new Date(snapshot.visibleFrom * 1000).toISOString();
    wire.visible_to = new Date(snapshot.visibleTo * 1000).toISOString();
  }
  return wire;
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
    focus: raw.focus === null ? null : mapChartFocus(raw.focus),
  };
}

interface RawDrawing {
  id: number;
  symbol: string;
  geometry: Record<string, unknown> & { kind: string };
  label: string | null;
  color: string | null;
  hidden?: boolean;
  created_at: string;
  updated_at: string;
}

function mapDrawingGeometry(raw: RawDrawing["geometry"]): AgentDrawingGeometry | null {
  // A `kind` this terminal has no shape for is skipped, not thrown on: a module deployed
  // ahead of the terminal may publish a fourth shape, and one unknown object must not
  // take the whole read — and with it every drawing the chart *can* draw — down with it
  // (design.md, "Agent sprzed zmiany wobec terminala po zmianie", read the other way
  // round).
  if (raw.kind === "level") {
    return {
      kind: "level",
      price: raw.price as number,
      at: raw.at == null ? null : parseIsoToEpochSeconds(raw.at as string),
    };
  }
  if (raw.kind === "zone") {
    return {
      kind: "zone",
      top: raw.top as number,
      bottom: raw.bottom as number,
      from: raw.from == null ? null : parseIsoToEpochSeconds(raw.from as string),
      to: raw.to == null ? null : parseIsoToEpochSeconds(raw.to as string),
    };
  }
  if (raw.kind === "trendline") {
    const a = raw.a as { time: string; price: number };
    const b = raw.b as { time: string; price: number };
    return {
      kind: "trendline",
      a: { time: parseIsoToEpochSeconds(a.time), price: a.price },
      b: { time: parseIsoToEpochSeconds(b.time), price: b.price },
    };
  }
  return null;
}

function mapDrawing(raw: RawDrawing): AgentChartDrawing | null {
  const geometry = mapDrawingGeometry(raw.geometry);
  if (geometry === null) return null;
  return {
    id: raw.id,
    symbol: raw.symbol,
    geometry,
    label: raw.label,
    color: raw.color,
    // An absent field reads as lit, never as an object to leave off the chart: a terminal
    // deployed ahead of the module would otherwise draw an empty instrument for the
    // length of one deploy (design.md, "Terminal wdrożony przed agentem").
    hidden: raw.hidden ?? false,
    createdAt: parseIsoToEpochSeconds(raw.created_at),
    updatedAt: parseIsoToEpochSeconds(raw.updated_at),
  };
}

function drawingPatchToWire(
  patch: AgentDrawingPatch,
): Record<string, number | string | boolean> {
  const wire: Record<string, number | string | boolean> = {};
  if (patch.price !== undefined) wire.price = patch.price;
  if (patch.top !== undefined) wire.top = patch.top;
  if (patch.bottom !== undefined) wire.bottom = patch.bottom;
  if (patch.aPrice !== undefined) wire.a_price = patch.aPrice;
  if (patch.bPrice !== undefined) wire.b_price = patch.bPrice;
  if (patch.label !== undefined) wire.label = patch.label;
  if (patch.hidden !== undefined) wire.hidden = patch.hidden;
  return wire;
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

// 422: a model id the catalogue does not know, or a patch with none at all — the module
// understood the request and declined it, same as a resolution the archive will not take
// on.
const mapStatus = statusMapper({ 404: "not-found", 422: "refused" });

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

    async getUnclaimedToolCalls(id, signal) {
      const raw = await http.json<RawToolCall[]>(
        `${httpBase}/sessions/${id}/unclaimed-tool-calls`,
        { signal },
      );
      return raw.map(mapToolCall);
    },

    async sendMessage(id, content, signal, chart = null) {
      const response = await http.send(`${httpBase}/sessions/${id}/messages`, {
        method: "POST",
        body: chart === null ? { content } : { content, chart: chartSnapshotToWire(chart) },
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

    async listDrawings(symbol, signal) {
      const raw = await http.json<RawDrawing[]>(
        `${httpBase}/drawings?symbol=${encodeURIComponent(symbol)}`,
        { signal },
      );
      return raw.map(mapDrawing).filter((drawing): drawing is AgentChartDrawing => drawing !== null);
    },

    async patchDrawing(id, patch, signal) {
      const raw = await http.json<RawDrawing>(`${httpBase}/drawings/${id}`, {
        method: "PATCH",
        body: drawingPatchToWire(patch),
        signal,
      });
      const mapped = mapDrawing(raw);
      if (mapped === null) {
        // The corrected drawing came back in a shape this terminal cannot draw. Skipping
        // it the way a list read does would leave the caller with nothing to show and no
        // reason why.
        throw new MarketDataError("unknown", `drawing ${id} came back in an unknown shape`);
      }
      return mapped;
    },

    async deleteDrawing(id, signal) {
      await http.send(`${httpBase}/drawings/${id}`, { method: "DELETE", signal });
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
export const agentApi: AgentApi = createAgentApi(resolveEndpoints().workbenchHttp, identity);
