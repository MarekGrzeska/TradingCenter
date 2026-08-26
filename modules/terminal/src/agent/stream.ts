/**
 * The agent's turn read as it arrives — `fetch` + `ReadableStream`, not `EventSource`: the route is a `POST` and
 * carries an `Authorization` header. `parseSseFrame` is the whole of what is agent-specific; the reader is shared.
 */

import { readSseStream } from "../data/sseStream";
import { mapToolCall, type AgentToolCall, type RawToolCall } from "./toolCall";

export type AgentStreamEvent =
  | { kind: "fragment"; text: string }
  | { kind: "toolCall"; call: AgentToolCall }
  | { kind: "complete"; incomplete: boolean }
  | { kind: "error"; message: string }
  /** The operator ended this turn. Carries nothing: what was said is already on screen,
   *  and the reply itself comes back from the transcript like every other one. */
  | { kind: "stopped" };

/**
 * One frame to a typed event, or `null` for a keepalive comment, a blank frame, or an event name this
 * terminal has no use for.
 */
export function parseSseFrame(frame: string): AgentStreamEvent | null {
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
    case "fragment":
      return { kind: "fragment", text: String(payload.text ?? "") };
    case "tool_call":
      // The module publishes one shape for a call whether it arrives here or on a reloaded transcript, so
      // both paths land in the same mapper and the panel cannot be shown two versions of one call.
      return { kind: "toolCall", call: mapToolCall(payload as unknown as RawToolCall) };
    case "complete":
      return { kind: "complete", incomplete: Boolean(payload.incomplete) };
    case "error":
      return { kind: "error", message: String(payload.message ?? "") };
    case "stopped":
      return { kind: "stopped" };
    default:
      return null;
  }
}

/**
 * A turn's body as the events it carries, stopping at the first terminal one. A body ending with none of them just
 * ends the generator: the caller is where that silence becomes an error, since only it knows what arrived.
 */
export function readAgentStream(body: ReadableStream<Uint8Array>): AsyncGenerator<AgentStreamEvent> {
  return readSseStream(
    body,
    parseSseFrame,
    (event) => event.kind === "complete" || event.kind === "error" || event.kind === "stopped",
  );
}
