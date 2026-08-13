/**
 * The agent's turn, read as it arrives — `fetch` + `ReadableStream`, not `EventSource`:
 * the route is a `POST` and carries an `Authorization` header, neither of which
 * `EventSource` can do (design.md, "Odpowiedź strumieniem: fetch + ReadableStream, nie
 * EventSource"). Nothing here is agent-specific vocabulary beyond the four event kinds
 * the module actually sends — `_sse` in `agent/routers/sessions.py`.
 *
 * Split in two on purpose. `splitSseFrames`/`parseSseFrame` are pure string functions —
 * a frame arriving split across two network chunks is a plain-string test, no stream
 * required. `readAgentStream` is the one place a real `ReadableStream` is touched, and it
 * carries nothing worth testing on its own beyond wiring the two together.
 */

import { mapToolCall, type AgentToolCall, type RawToolCall } from "./toolCall";

export type AgentStreamEvent =
  | { kind: "fragment"; text: string }
  | { kind: "toolCall"; call: AgentToolCall }
  | { kind: "complete"; incomplete: boolean }
  | { kind: "error"; message: string };

/**
 * Buffers raw SSE bytes and splits them into frames on the blank-line terminator
 * (`\n\n`) every real frame ends with. The last, possibly incomplete, piece is handed
 * back as `remainder` for the caller to prepend to the next chunk — a frame's `data:`
 * line has no reason to land inside one network read.
 */
export function splitSseFrames(buffer: string): { frames: string[]; remainder: string } {
  const parts = buffer.split("\n\n");
  const remainder = parts.pop() ?? "";
  return { frames: parts, remainder };
}

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
    default:
      return null;
  }
}

/**
 * Reads a turn's body as the sequence of events it carries, stopping at whichever
 * terminal event arrives first (`complete` or `error` — `agent-chat` spec, "three
 * distinguishable event kinds"). A body that ends with neither — the connection
 * dropped — simply ends the generator without one; the caller (`agentChatStore`) is
 * where that silence becomes a visible error, since only it knows what, if anything,
 * arrived before the drop.
 */
export async function* readAgentStream(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<AgentStreamEvent> {
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
        const event = parseSseFrame(frame);
        if (event === null) continue;
        yield event;
        if (event.kind === "complete" || event.kind === "error") return;
      }
    }
  } finally {
    reader.releaseLock();
  }
}
