/**
 * Reading an SSE body, without knowing what is in it.
 *
 * Two modules stream into this terminal — a turn from `agent`, a run's progress from
 * `teams` — and their vocabularies have nothing in common: four event kinds there, five
 * here, no two named alike. What they *did* have in common was this loop, written twice:
 * take the reader, decode each chunk, buffer whatever is left of a frame that arrived
 * split across two network reads, hand the whole frames to a parser, release the lock.
 *
 * So the loop is shared and the vocabulary is not — `parseFrame` stays in the module
 * that knows what its module sends, which is the objection the twin in `teams/runs.ts`
 * was written under and the reason this is not one parser with a mode flag.
 */

/**
 * Buffers raw SSE bytes and splits them into frames on the blank line (`\n\n`) every
 * frame ends with. The last, possibly incomplete, piece comes back as `remainder` for the
 * caller to prepend to the next chunk — a `data:` line has no reason to land inside one
 * network read.
 *
 * Pure, so a frame arriving in pieces is a plain-string test with no stream in it.
 */
export function splitSseFrames(buffer: string): { frames: string[]; remainder: string } {
  const parts = buffer.split("\n\n");
  const remainder = parts.pop() ?? "";
  return { frames: parts, remainder };
}

/**
 * The events a body carries, in order, as whatever `parseFrame` makes of them. A frame it
 * answers `null` for is skipped — a keepalive comment (`: ping`, sent so App Service does
 * not drop a connection that a model's thinking left quiet), a blank frame, an event name
 * this terminal has no use for.
 *
 * `isTerminal` stops the read at the first event that says the stream is over rather than
 * waiting for the body to close. A body that ends without one simply ends the generator:
 * that is a dropped connection, and the caller is the only one that knows what had
 * already arrived, so it is the caller that turns the silence into something the operator
 * sees.
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
