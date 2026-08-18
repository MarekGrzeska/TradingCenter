import { describe, expect, it } from "vitest";
import { splitSseFrames } from "../data/sseStream";
import { parseSseFrame, readAgentStream } from "./stream";

function byteStream(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  let index = 0;
  return new ReadableStream({
    pull(controller) {
      if (index >= chunks.length) {
        controller.close();
        return;
      }
      controller.enqueue(encoder.encode(chunks[index++]));
    },
  });
}

async function collect(body: ReadableStream<Uint8Array>) {
  const events = [];
  for await (const event of readAgentStream(body)) events.push(event);
  return events;
}

describe("splitSseFrames", () => {
  it("splits complete frames and holds back an unterminated tail", () => {
    const { frames, remainder } = splitSseFrames(
      'event: fragment\ndata: {"text":"a"}\n\nevent: fragment\ndata: {"text":"b"}\n\nevent: complete\ndata: {',
    );
    expect(frames).toEqual([
      'event: fragment\ndata: {"text":"a"}',
      'event: fragment\ndata: {"text":"b"}',
    ]);
    expect(remainder).toBe("event: complete\ndata: {");
  });

  it("holds the whole buffer back when no frame has terminated yet", () => {
    const { frames, remainder } = splitSseFrames("event: frag");
    expect(frames).toEqual([]);
    expect(remainder).toBe("event: frag");
  });
});

describe("parseSseFrame", () => {
  it("reads a fragment", () => {
    expect(parseSseFrame('event: fragment\ndata: {"text":"hello"}')).toEqual({
      kind: "fragment",
      text: "hello",
    });
  });

  it("reads a completion, incomplete or not", () => {
    expect(parseSseFrame('event: complete\ndata: {"incomplete":false}')).toEqual({
      kind: "complete",
      incomplete: false,
    });
    expect(parseSseFrame('event: complete\ndata: {"incomplete":true}')).toEqual({
      kind: "complete",
      incomplete: true,
    });
  });

  it("reads an error", () => {
    expect(parseSseFrame('event: error\ndata: {"message":"the model call failed"}')).toEqual({
      kind: "error",
      message: "the model call failed",
    });
  });

  it("reads a tool call into the same shape the transcript hands back", () => {
    const frame =
      "event: tool_call\ndata: " +
      JSON.stringify({
        round_index: 1,
        position: 0,
        tool_name: "get_candles",
        arguments: { symbol: "US100", resolution: "DAY" },
        outcome: "ok",
        result_text: '{"candles": 78}',
        duration_ms: 240,
        source: "server",
      });

    expect(parseSseFrame(frame)).toEqual({
      kind: "toolCall",
      call: {
        roundIndex: 1,
        position: 0,
        name: "get_candles",
        arguments: { symbol: "US100", resolution: "DAY" },
        outcome: "ok",
        resultText: '{"candles": 78}',
        durationMs: 240,
        source: "server",
      },
    });
  });

  it("keeps an outcome it has no name for out of the four it does", () => {
    // A fifth kind rendered as one of the four would say something the module did not:
    // an unreachable server shown as a refusal reads as "the archive says no". And it must
    // not land on `unknown` either — that one now means an order may be on the account.
    const frame =
      "event: tool_call\ndata: " +
      JSON.stringify({
        round_index: 0,
        position: 0,
        tool_name: "get_candles",
        arguments: {},
        outcome: "throttled",
        result_text: "slow down",
        duration_ms: 1,
      });

    const event = parseSseFrame(frame);

    expect(event).toMatchObject({ kind: "toolCall", call: { outcome: "unrecognised" } });
  });

  it("carries an unknown outcome through as itself", () => {
    // `agent-trading` spec: the call may have landed. Softening this into "unavailable"
    // would tell the operator nothing happened, which is the one thing nobody knows.
    const frame =
      "event: tool_call\ndata: " +
      JSON.stringify({
        round_index: 0,
        position: 0,
        tool_name: "place_order",
        arguments: { symbol: "US100" },
        outcome: "unknown",
        result_text: "may have gone through",
        duration_ms: 31000,
      });

    const event = parseSseFrame(frame);

    expect(event).toMatchObject({ kind: "toolCall", call: { outcome: "unknown" } });
  });

  it("names the module's own tool apart from a server one", () => {
    const frame =
      "event: tool_call\ndata: " +
      JSON.stringify({
        round_index: 0,
        position: 0,
        tool_name: "set_chart",
        arguments: {},
        outcome: "ok",
        result_text: "the operator's chart is now set to symbol US100.",
        duration_ms: 4,
        source: "module",
      });

    expect(parseSseFrame(frame)).toMatchObject({ kind: "toolCall", call: { source: "module" } });
  });

  it("keeps a source it has no name for out of the two it does", () => {
    const frame =
      "event: tool_call\ndata: " +
      JSON.stringify({
        round_index: 0,
        position: 0,
        tool_name: "get_candles",
        arguments: {},
        outcome: "ok",
        result_text: "78 candles",
        duration_ms: 1,
        source: "cache",
      });

    expect(parseSseFrame(frame)).toMatchObject({ kind: "toolCall", call: { source: "unknown" } });
  });

  it("ignores the keepalive comment", () => {
    expect(parseSseFrame(": ping")).toBeNull();
  });

  it("ignores a blank frame", () => {
    expect(parseSseFrame("")).toBeNull();
    expect(parseSseFrame("   ")).toBeNull();
  });

  it("ignores an event this terminal has no use for", () => {
    expect(parseSseFrame('event: something-new\ndata: {"x":1}')).toBeNull();
  });
});

describe("readAgentStream", () => {
  it("yields fragments arriving whole, one event per frame", async () => {
    const events = await collect(
      byteStream([
        'event: fragment\ndata: {"text":"why is "}\n\n',
        'event: fragment\ndata: {"text":"BTC flat"}\n\n',
        'event: complete\ndata: {"incomplete":false}\n\n',
      ]),
    );
    expect(events).toEqual([
      { kind: "fragment", text: "why is " },
      { kind: "fragment", text: "BTC flat" },
      { kind: "complete", incomplete: false },
    ]);
  });

  // The point of the exercise: a frame's `data:` line lands on the wrong side of a
  // network read, and the parser still produces exactly one event for it.
  it("reassembles a frame split across two chunks", async () => {
    const events = await collect(
      byteStream([
        'event: fragment\ndata: {"te',
        'xt":"hello"}\n\nevent: complete\ndata: {"incomplete":false}\n\n',
      ]),
    );
    expect(events).toEqual([
      { kind: "fragment", text: "hello" },
      { kind: "complete", incomplete: false },
    ]);
  });

  it("skips keepalive comments between fragments", async () => {
    const events = await collect(
      byteStream([
        'event: fragment\ndata: {"text":"a"}\n\n',
        ": ping\n\n",
        'event: complete\ndata: {"incomplete":false}\n\n',
      ]),
    );
    expect(events).toEqual([
      { kind: "fragment", text: "a" },
      { kind: "complete", incomplete: false },
    ]);
  });

  it("stops at the error event without reading further", async () => {
    const events = await collect(
      byteStream([
        'event: fragment\ndata: {"text":"a"}\n\n',
        'event: error\ndata: {"message":"the model call failed"}\n\n',
        'event: fragment\ndata: {"text":"unreachable — must not be yielded"}\n\n',
      ]),
    );
    expect(events).toEqual([
      { kind: "fragment", text: "a" },
      { kind: "error", message: "the model call failed" },
    ]);
  });

  it("ends quietly when the connection closes with no terminal event", async () => {
    const events = await collect(
      byteStream(['event: fragment\ndata: {"text":"a"}\n\n']),
    );
    expect(events).toEqual([{ kind: "fragment", text: "a" }]);
  });
});
