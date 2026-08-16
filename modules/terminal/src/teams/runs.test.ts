import { describe, expect, it } from "vitest";
import { attachAgentKeys, parseRunFrame, splitSseFrames, type TeamRunStep } from "./runs";

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

describe("attachAgentKeys", () => {
  const calls = [
    { runStepId: 1, roundIndex: 0, position: 0, toolName: "candles", outcome: "ok", durationMs: 5 },
    { runStepId: 99, roundIndex: 0, position: 0, toolName: "candles", outcome: "ok", durationMs: 5 },
  ];

  it("names the agent whose step made the call", () => {
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
      },
    ]);
  });
});
