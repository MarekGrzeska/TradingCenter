/**
 * One tool call the agent made, and the one mapper that produces it.
 *
 * Its own file rather than a corner of `agentApi.ts` because both wire paths need it and
 * they need each other: a call arrives mid-turn through `stream.ts` and again, identical,
 * on a reloaded transcript through `agentApi.ts`. The module publishes a single shape for
 * both (`agent/contract.py`, `ToolCallOut`), and mapping it in one place is what makes
 * "what the stream showed" and "what the transcript holds" the same object here too.
 */

/** The three the module distinguishes (`ToolOutcomeKind` in `agent/tools/client.py`),
 *  plus a name for one it does not yet. A fourth kind arriving must not be silently
 *  rendered as one of the three — an unreachable server shown as a refusal reads as "the
 *  archive says no", which is the confusion this whole panel exists to prevent. */
export type ToolOutcome = "ok" | "refused" | "unavailable" | "unknown";

/** Which one ran the call — the module's own `set_chart`, or one market-mcp announced
 *  (`agent/contract.py`, `ToolCallOut.source`; `agent-tools` spec, "ślad wywołania mówi,
 *  które z nich zostało wykonane przez ten moduł"). `"unknown"` for a value this build
 *  does not recognise, the same defensive fallback `mapOutcome` uses below. */
export type ToolCallSource = "server" | "module" | "unknown";

export interface AgentToolCall {
  /** Which round of the turn this call belonged to, and where within it. Together they
   *  say whether three calls were one round of three or three rounds of one — a model
   *  surveying, or a model iterating. */
  roundIndex: number;
  position: number;
  name: string;
  arguments: Record<string, unknown>;
  outcome: ToolOutcome;
  /** The text the model itself was handed, not a summary of it. */
  resultText: string;
  durationMs: number;
  source: ToolCallSource;
}

export interface RawToolCall {
  round_index: number;
  position: number;
  tool_name: string;
  arguments: Record<string, unknown>;
  outcome: string;
  result_text: string;
  duration_ms: number;
  source: string;
}

export function mapToolCall(raw: RawToolCall): AgentToolCall {
  return {
    roundIndex: raw.round_index,
    position: raw.position,
    name: raw.tool_name,
    arguments: raw.arguments ?? {},
    outcome: mapOutcome(raw.outcome),
    resultText: raw.result_text,
    durationMs: raw.duration_ms,
    source: mapSource(raw.source),
  };
}

function mapOutcome(outcome: string): ToolOutcome {
  switch (outcome) {
    case "ok":
    case "refused":
    case "unavailable":
      return outcome;
    default:
      return "unknown";
  }
}

function mapSource(source: string): ToolCallSource {
  switch (source) {
    case "server":
    case "module":
      return source;
    default:
      return "unknown";
  }
}
