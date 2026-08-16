/**
 * The run half of the teams wire: what a run, a step and a tool call look like on this
 * side, and how the module's progress stream is read.
 *
 * Kept apart from `teamsApi.ts` — which maps the catalogue half — because a run arrives
 * through two doors that carry the same facts: a JSON read (`/runs/{id}`, `/steps`,
 * `/tool-calls`) and an SSE frame on `/runs/{id}/events`. Both land in the mappers below,
 * so the monitor cannot be shown two different versions of one run depending on whether
 * it was watching when the step finished.
 *
 * `splitSseFrames` and the reader are a deliberate twin of `agent/stream.ts` rather than
 * a shared helper. What the two tabs share is six lines of string splitting; what they do
 * not share is the vocabulary — four event kinds there, five here, none with the same
 * name — and a common parser would have to be told which set to expect, which is the
 * whole of what it would be doing.
 */

import type { components } from "../data/contract.teams.generated";
import { parseIsoToEpochSeconds } from "../data/time";

type Wire = components["schemas"];
type RawRun = Wire["RunOut"];
type RawStep = Wire["RunStepOut"];
type RawToolCall = Wire["ToolCallOut"];

/** `runs.status` — a plain string here, as on the module's wire, where the CHECK
 *  constraint is the enforcement. `pending`, `running`, `completed`, `failed`,
 *  `cancelled`; a value this terminal does not know still renders as itself rather than
 *  as a blank. */
export type RunStatus = string;

/** `run_steps.status` — `pending`, `running`, `completed` or `failed`. */
export type StepStatus = string;

export interface TeamRun {
  id: number;
  /** The revision the run works on — **not** the team's latest. Reading the definition
   *  by this id is what keeps the picture and the run the same graph (specs/teams-runs,
   *  "Przebieg odbywa się na rewizji, nie na zespole"). */
  teamRevisionId: number;
  status: RunStatus;
  /** Why it stopped, when it did not simply finish — a cost ceiling, a timeout, the
   *  operator. Shown as it arrived: the module writes the sentence. */
  stoppedReason: string | null;
  startedAt: number | null;
  finishedAt: number | null;
  createdAt: number;
}

export interface TeamRunStep {
  id: number;
  runId: number;
  agentKey: string;
  status: StepStatus;
  /** What this agent produced, once it has. */
  output: string | null;
  rounds: number;
  startedAt: number | null;
  finishedAt: number | null;
}

/** One tool call, keyed by the agent that made it — which is how the monitor groups
 *  them. The stream says the agent outright; a recorded call names its step, and
 *  `attachAgentKeys` is where that becomes the same thing. */
export interface TeamRunToolCall {
  agentKey: string;
  roundIndex: number;
  position: number;
  toolName: string;
  /** `ok`, `refused` or `unavailable` — the module's three outcomes, and the reason a
   *  refusal and an outage are not one entry (specs/teams-tool-access). */
  outcome: string;
  durationMs: number;
}

/** A call read back from `/runs/{id}/tool-calls`, which names the step rather than the
 *  agent — the row's own shape. */
export interface RecordedToolCall extends Omit<TeamRunToolCall, "agentKey"> {
  runStepId: number;
}

export type RunStreamEvent =
  /** Where the run is now, sent first on every connection — which is what makes closing
   *  and reopening the view show the current state rather than the state at the drop
   *  (specs/teams-runs). */
  | { kind: "snapshot"; run: TeamRun; steps: TeamRunStep[] }
  | { kind: "stepStarted"; agentKey: string }
  | { kind: "stepFinished"; agentKey: string; status: StepStatus; output: string | null }
  | { kind: "toolCall"; call: TeamRunToolCall }
  | { kind: "runFinished"; status: RunStatus; stoppedReason: string | null };

function epochOrNull(iso: string | null): number | null {
  return iso === null ? null : parseIsoToEpochSeconds(iso);
}

export function mapRun(raw: RawRun): TeamRun {
  return {
    id: raw.id,
    teamRevisionId: raw.team_revision_id,
    status: raw.status,
    stoppedReason: raw.stopped_reason,
    startedAt: epochOrNull(raw.started_at),
    finishedAt: epochOrNull(raw.finished_at),
    createdAt: parseIsoToEpochSeconds(raw.created_at),
  };
}

export function mapRunStep(raw: RawStep): TeamRunStep {
  return {
    id: raw.id,
    runId: raw.run_id,
    agentKey: raw.agent_key,
    status: raw.status,
    output: raw.output,
    rounds: raw.rounds,
    startedAt: epochOrNull(raw.started_at),
    finishedAt: epochOrNull(raw.finished_at),
  };
}

export function mapRecordedToolCall(raw: RawToolCall): RecordedToolCall {
  return {
    runStepId: raw.run_step_id,
    roundIndex: raw.round_index,
    position: raw.position,
    toolName: raw.tool_name,
    outcome: raw.outcome,
    durationMs: raw.duration_ms,
  };
}

/**
 * Recorded calls, given the agent key their step belongs to.
 *
 * A call whose step is not among the ones handed in is dropped rather than shown under
 * an invented name — it can only mean the two reads crossed a step being created, and
 * the next snapshot carries both.
 */
export function attachAgentKeys(
  calls: RecordedToolCall[],
  steps: TeamRunStep[],
): TeamRunToolCall[] {
  const agentOf = new Map(steps.map((step) => [step.id, step.agentKey]));
  return calls.flatMap(({ runStepId, ...call }) => {
    const agentKey = agentOf.get(runStepId);
    return agentKey === undefined ? [] : [{ agentKey, ...call }];
  });
}

/**
 * Buffers raw SSE bytes and splits them on the blank line every frame ends with. The
 * last, possibly incomplete, piece comes back as `remainder` for the caller to prepend
 * to the next chunk — a `data:` line has no reason to land inside one network read.
 */
export function splitSseFrames(buffer: string): { frames: string[]; remainder: string } {
  const parts = buffer.split("\n\n");
  const remainder = parts.pop() ?? "";
  return { frames: parts, remainder };
}

/**
 * One frame to a typed event, or `null` for a keepalive comment (`: ping`, sent every 15s
 * so App Service does not drop a connection an agent's thinking left quiet), a blank
 * frame, or an event name this terminal has no use for.
 */
export function parseRunFrame(frame: string): RunStreamEvent | null {
  if (frame.trim() === "" || frame.startsWith(":")) return null;

  let event = "";
  let data = "";
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) event = line.slice("event:".length).trim();
    else if (line.startsWith("data:")) data = line.slice("data:".length).trim();
  }
  if (event === "") return null;

  const payload = data === "" ? {} : (JSON.parse(data) as Record<string, unknown>);
  switch (event) {
    case "snapshot": {
      const snapshot = payload as unknown as { run: RawRun; steps: RawStep[] };
      return {
        kind: "snapshot",
        run: mapRun(snapshot.run),
        steps: snapshot.steps.map(mapRunStep),
      };
    }
    case "step_started":
      return { kind: "stepStarted", agentKey: String(payload.agent_key ?? "") };
    case "step_finished":
      return {
        kind: "stepFinished",
        agentKey: String(payload.agent_key ?? ""),
        status: String(payload.status ?? ""),
        output: payload.output === null || payload.output === undefined
          ? null
          : String(payload.output),
      };
    case "tool_call":
      return {
        kind: "toolCall",
        call: {
          agentKey: String(payload.agent_key ?? ""),
          roundIndex: Number(payload.round_index ?? 0),
          position: Number(payload.position ?? 0),
          toolName: String(payload.tool_name ?? ""),
          outcome: String(payload.outcome ?? ""),
          durationMs: Number(payload.duration_ms ?? 0),
        },
      };
    case "run_finished":
      return {
        kind: "runFinished",
        status: String(payload.status ?? ""),
        stoppedReason:
          payload.stopped_reason === null || payload.stopped_reason === undefined
            ? null
            : String(payload.stopped_reason),
      };
    default:
      return null;
  }
}

/**
 * The events a run's stream carries, until the module closes it.
 *
 * It closes it itself once the run is over — and immediately, with nothing but the
 * snapshot, for a run that was already over when the view opened. A body that ends
 * without `run_finished` is a dropped connection; the caller is where that becomes
 * something the operator sees, since only it knows what arrived before the drop.
 */
export async function* readRunStream(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<RunStreamEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const { frames, remainder } = splitSseFrames(buffer);
      buffer = remainder;
      for (const frame of frames) {
        const event = parseRunFrame(frame);
        if (event !== null) yield event;
      }
    }
  } finally {
    reader.releaseLock();
  }
}
