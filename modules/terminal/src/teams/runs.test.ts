import { describe, expect, it } from "vitest";
import {
  attachAgentKeys,
  outcomeOf,
  parseRunFrame,
  splitSseFrames,
  stopCause,
  type TeamRunStep,
  type TeamTrade,
} from "./runs";

/**
 * The pure half of `runs.ts`. A frame arriving split across two network reads, and a
 * recorded call that names a step rather than an agent, are both plain-value problems —
 * no stream and no component required to state them.
 */

function step(id: number, agentKey: string): TeamRunStep {
  return {
    id,
    runId: 7,
    agentKey,
    status: "completed",
    output: null,
    rounds: 1,
    startedAt: null,
    finishedAt: null,
  };
}

describe("splitSseFrames", () => {
  it("hands back the trailing piece rather than parsing half a frame", () => {
    const { frames, remainder } = splitSseFrames(
      'event: step_started\ndata: {"agent_key":"a"}\n\nevent: tool_call\ndata: {"agent',
    );

    expect(frames).toEqual(['event: step_started\ndata: {"agent_key":"a"}']);
    expect(remainder).toBe('event: tool_call\ndata: {"agent');
  });
});

describe("parseRunFrame", () => {
  it("reads the opening snapshot into the run and its steps", () => {
    const frame =
      "event: snapshot\ndata: " +
      JSON.stringify({
        run: {
          id: 7,
          team_revision_id: 9,
          status: "running",
          stopped_reason: null,
          started_at: "2026-08-16T10:00:00Z",
          finished_at: null,
          created_at: "2026-08-16T10:00:00Z",
        },
        steps: [
          {
            id: 1,
            run_id: 7,
            agent_key: "scout",
            status: "completed",
            output: "US100 is trending",
            rounds: 2,
            started_at: "2026-08-16T10:00:01Z",
            finished_at: "2026-08-16T10:00:40Z",
          },
        ],
      });

    const event = parseRunFrame(frame);

    expect(event).toMatchObject({
      kind: "snapshot",
      run: { id: 7, teamRevisionId: 9, status: "running", startedAt: 1_786_874_400 },
      steps: [{ agentKey: "scout", output: "US100 is trending", rounds: 2 }],
    });
  });

  it("reads a finished step, a tool call and the run's own end", () => {
    expect(
      parseRunFrame('event: step_finished\ndata: {"agent_key":"judge","status":"completed","output":"buy"}'),
    ).toEqual({ kind: "stepFinished", agentKey: "judge", status: "completed", output: "buy" });

    expect(
      parseRunFrame(
        'event: tool_call\ndata: {"agent_key":"scout","round_index":1,"position":0,' +
          '"tool_name":"candles","outcome":"refused","duration_ms":12}',
      ),
    ).toEqual({
      kind: "toolCall",
      call: {
        agentKey: "scout",
        roundIndex: 1,
        position: 0,
        toolName: "candles",
        outcome: "refused",
        durationMs: 12,
      },
    });

    expect(
      parseRunFrame(
        'event: run_finished\ndata: {"status":"failed","stopped_reason":"reached its cost limit"}',
      ),
    ).toEqual({ kind: "runFinished", status: "failed", stoppedReason: "reached its cost limit" });
  });

  it("ignores a keepalive, a blank frame and an event kind it has no use for", () => {
    expect(parseRunFrame(": ping")).toBeNull();
    expect(parseRunFrame("")).toBeNull();
    expect(parseRunFrame('event: something-new\ndata: {"x":1}')).toBeNull();
  });
});

describe("what came of an order", () => {
  function trade(status: string, resultStatus: string | null = null): TeamTrade {
    return {
      id: 1,
      runId: 7,
      agentKey: "trader",
      toolName: "an order tool",
      symbol: "US100",
      direction: "BUY",
      size: "1",
      level: null,
      status,
      resultStatus,
      providerOrderId: null,
      reference: null,
      createdAt: 1_786_874_400,
      settledAt: null,
    };
  }

  it("says the provider's own word when the order settled", () => {
    expect(outcomeOf(trade("settled", "FILLED"), true)).toEqual({ text: "FILLED", known: true });
  });

  it("shows an order of unknown outcome as unknown, not as a failure", () => {
    // specs/terminal-teams — the module writes `unknown` when a call's reply never came,
    // which is not the same statement as a refusal and must not read like one.
    expect(outcomeOf(trade("unknown"), true)).toEqual({ text: "outcome unknown", known: false });
    expect(outcomeOf(trade("refused"), true)).toEqual({ text: "refused", known: true });
  });

  it("reads a row still saying `sent` by whether the run is over", () => {
    // While the run works it is an order on its way; once the run is over it is an order
    // the module never learned the fate of, which is what its own contract says of the
    // row (`0004_trades.py`).
    expect(outcomeOf(trade("sent"), false)).toEqual({ text: "sent", known: true });
    expect(outcomeOf(trade("sent"), true)).toEqual({ text: "outcome unknown", known: false });
  });
});

describe("stopCause", () => {
  it("tells the order limit from the cost limit", () => {
    // The two sentences the module writes (`runner/trading.py`, `runner/cost.py`). Only
    // the heading above the reason is picked here — the sentence itself always travels
    // intact, which is why a reworded one costs a heading and nothing else.
    expect(stopCause("the run's order limit was reached: 2 of 2 allowed placed.")).toBe("orders");
    expect(stopCause("the run's cost limit was reached: 2.01 spent of 2.00 allowed.")).toBe("cost");
    expect(stopCause("the operator interrupted the run")).toBe("other");
    expect(stopCause(null)).toBeNull();
  });
});

describe("attachAgentKeys", () => {
  const detail = { arguments: { symbol: "US100" }, resultText: "12 candles" };
  const calls = [
    { runStepId: 1, roundIndex: 0, position: 0, toolName: "candles", outcome: "ok", durationMs: 5, detail },
    { runStepId: 99, roundIndex: 0, position: 0, toolName: "candles", outcome: "ok", durationMs: 5, detail },
  ];

  it("names the agent whose step made the call, and keeps what it was given and answered", () => {
    expect(attachAgentKeys(calls, [step(1, "scout")])).toEqual([
      // The call under a step nobody handed in is dropped rather than shown under an
      // invented name — the two reads crossed a step being created, and the next
      // snapshot carries both.
      {
        agentKey: "scout",
        roundIndex: 0,
        position: 0,
        toolName: "candles",
        outcome: "ok",
        durationMs: 5,
        detail,
      },
    ]);
  });
});
