/**
 * The agent's turn, read as it arrives — `fetch` + `ReadableStream`, not `EventSource`:
 * the route is a `POST` and carries an `Authorization` header, neither of which
 * `EventSource` can do (design.md, "Odpowiedź strumieniem: fetch + ReadableStream, nie
 * EventSource"). Nothing here is agent-specific vocabulary beyond the four event kinds
 * the module actually sends — `_sse` in `agent/routers/sessions.py`.
 *
 * `parseSseFrame` is a pure string function and is the whole of what is agent-specific
 * here — the reading itself lives in `data/sseStream.ts`, shared with the run stream on
 * the teams side, which knows a different five event names and none of these.
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
 * One frame to a typed event, or `null` for a keepalive comment (`: ping`, sent every
 * `_KEEPALIVE_SECONDS` so App Service does not drop an idle connection — design.md), a
 * blank frame, or an event name this terminal has no use for.
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
      // The module publishes one shape for a call whether it arrives here or on a
      // reloaded transcript (`agent/contract.py`, `ToolCallOut`), so both paths land in
      // the same mapper and the panel cannot be shown two different versions of one call.
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
 * Reads a turn's body as the sequence of events it carries, stopping at whichever
 * terminal event arrives first — `complete`, `error`, or `stopped`, the three endings a
 * turn has (`agent-chat` spec). A body that ends with none of them — the connection
 * dropped — simply ends the generator without one; the caller (`agentChatStore`) is
 * where that silence becomes a visible error, since only it knows what, if anything,
 * arrived before the drop.
 */
export function readAgentStream(body: ReadableStream<Uint8Array>): AsyncGenerator<AgentStreamEvent> {
  return readSseStream(
    body,
    parseSseFrame,
    (event) => event.kind === "complete" || event.kind === "error" || event.kind === "stopped",
  );
}
