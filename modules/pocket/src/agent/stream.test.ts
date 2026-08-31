import { describe, expect, it } from "vitest";
import { parseSseFrame, readAgentStream, splitSseFrames } from "./stream";

function bodyOf(...chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

describe("splitting the bytes into frames", () => {
  it("hands back the piece that is not a whole frame yet", () => {
    expect(splitSseFrames("event: a\ndata: 1\n\nevent: b\ndata: 2")).toEqual({
      frames: ["event: a\ndata: 1"],
      remainder: "event: b\ndata: 2",
    });
  });
});

describe("one frame", () => {
  it("is nothing at all when it is a keepalive or blank", () => {
    expect(parseSseFrame(":keepalive")).toBeNull();
    expect(parseSseFrame("   ")).toBeNull();
  });

  it("is nothing when this build has no use for the event", () => {
    expect(parseSseFrame("event: usage\ndata: {}")).toBeNull();
  });

  it("carries the tool call in the shape a reloaded transcript uses", () => {
    const event = parseSseFrame(
      'event: tool_call\ndata: {"round_index":1,"position":0,"tool_name":"search_markets",' +
        '"arguments":{"q":"fed"},"outcome":"ok","result_text":"2 found","duration_ms":412,"source":"server"}',
    );

    expect(event).toEqual({
      kind: "toolCall",
      call: {
        roundIndex: 1,
        position: 0,
        name: "search_markets",
        arguments: { q: "fed" },
        outcome: "ok",
        resultText: "2 found",
        durationMs: 412,
        source: "server",
      },
    });
  });
});

describe("a turn", () => {
  it("arrives as its events, whatever the chunk boundaries were", async () => {
    const body = bodyOf(
      'event: fragment\ndata: {"text":"Bit"}\n\nevent: frag',
      'ment\ndata: {"text":"coin"}\n\n',
      'event: complete\ndata: {"incomplete":false}\n\n',
    );

    const seen = [];
    for await (const event of readAgentStream(body)) seen.push(event);

    expect(seen).toEqual([
      { kind: "fragment", text: "Bit" },
      { kind: "fragment", text: "coin" },
      { kind: "complete", incomplete: false },
    ]);
  });

  it("ends at the first terminal event, and does not read past it", async () => {
    const body = bodyOf(
      'event: error\ndata: {"message":"the model refused"}\n\n',
      'event: fragment\ndata: {"text":"never"}\n\n',
    );

    const seen = [];
    for await (const event of readAgentStream(body)) seen.push(event);

    expect(seen).toEqual([{ kind: "error", message: "the model refused" }]);
  });
});
