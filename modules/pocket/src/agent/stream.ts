/**
 * The agent's turn read as it arrives — `fetch` + `ReadableStream`, not `EventSource`: the route is a
 * `POST` and carries an `Authorization` header, and `EventSource` can do neither.
 */

import { mapToolCall, type AgentToolCall, type RawToolCall } from "./toolCall";

export type AgentStreamEvent =
  | { kind: "fragment"; text: string }
  | { kind: "toolCall"; call: AgentToolCall }
  | { kind: "complete"; incomplete: boolean }
  | { kind: "error"; message: string }
  /** The operator ended this turn. Carries nothing: what was said is already on screen, and the reply
   *  comes back from the transcript like every other one. */
  | { kind: "stopped" };

/** Splits raw SSE bytes into frames on the blank line each ends with; the last, possibly incomplete
 *  piece comes back as `remainder`. Pure, so a frame arriving in pieces is a plain-string test. */
export function splitSseFrames(buffer: string): { frames: string[]; remainder: string } {
  const parts = buffer.split("\n\n");
  const remainder = parts.pop() ?? "";
  return { frames: parts, remainder };
}

/** One frame to a typed event, or `null` for a keepalive comment, a blank frame, or an event name this
 *  screen has no use for. */
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
 * A turn's body as the events it carries, stopping at the first terminal one. A body ending with none
 * of them just ends the generator: the caller is where that silence becomes an error, since only it
 * knows what had already arrived.
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
        if (event.kind === "complete" || event.kind === "error" || event.kind === "stopped") {
          return;
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
