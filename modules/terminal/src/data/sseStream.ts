/**
 * Reading an SSE body without knowing what is in it: two modules stream here with nothing in common but this
 * loop. The vocabulary is not shared — `parseFrame` stays in the module that knows what its module sends.
 */

/**
 * Splits raw SSE bytes into frames on the blank line each ends with; the last, possibly incomplete piece comes
 * back as `remainder`. Pure, so a frame arriving in pieces is a plain-string test with no stream in it.
 */
export function splitSseFrames(buffer: string): { frames: string[]; remainder: string } {
  const parts = buffer.split("\n\n");
  const remainder = parts.pop() ?? "";
  return { frames: parts, remainder };
}

/**
 * A frame `parseFrame` answers `null` for is skipped — a keepalive, a blank, an event this terminal ignores.
 * A body ending without a terminal event just ends the generator: only the caller knows what had arrived.
 */
export async function* readSseStream<T>(
  body: ReadableStream<Uint8Array>,
  parseFrame: (frame: string) => T | null,
  isTerminal: (event: T) => boolean = () => false,
): AsyncGenerator<T> {
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
        const event = parseFrame(frame);
        if (event === null) continue;
        yield event;
        if (isTerminal(event)) return;
      }
    }
  } finally {
    reader.releaseLock();
  }
}
