import { describe, expect, it } from "vitest";
import { NO_HISTORY, kindForPatch, remember, undo } from "./editHistory";
import type { TeamDefinition, TeamLayout } from "./teamsApi";

function team(role: string): TeamDefinition {
  return {
    agents: [{ key: "agent-1", role, prompt: "", guidance: "", modelId: "a-model", tools: [] }],
    dependencies: [],
    limits: { runLimit: null, dailyLimit: null },
    trading: { maxOrderSize: null, ordersPerRun: null, ordersPerDay: null },
  };
}

function state(role: string, places: TeamLayout = new Map()) {
  return { definition: team(role), places };
}

describe("remembering an action", () => {
  it("hands back the state from before it, newest last", () => {
    let history = remember(NO_HISTORY, state("first"), "structure");
    history = remember(history, state("second"), "structure");

    expect(history.map((entry) => entry.state.definition.agents[0].role)).toEqual([
      "first",
      "second",
    ]);
  });

  it("keeps only the first of a run of typing, so one undo gives back the whole word", () => {
    // `edit` runs on every keystroke; without this, undo would walk back letter by letter
    // and the history would be nothing but one prompt.
    let history = remember(NO_HISTORY, state(""), "text:agent-1:role");
    history = remember(history, state("S"), "text:agent-1:role");
    history = remember(history, state("Sc"), "text:agent-1:role");

    expect(history).toHaveLength(1);
    expect(history[0].state.definition.agents[0].role).toBe("");
  });

  it("does not coalesce two actions of the same kind that are not typing", () => {
    // Two agents removed one after the other are two actions. Collapsing them would make
    // one undo do the work of two.
    let history = remember(NO_HISTORY, state("first"), "structure");
    history = remember(history, state("second"), "structure");

    expect(history).toHaveLength(2);
  });

  it("separates typing in one field from typing in another", () => {
    let history = remember(NO_HISTORY, state("a"), "text:agent-1:role");
    history = remember(history, state("b"), "text:agent-1:prompt");

    expect(history).toHaveLength(2);
  });

  it("remembers a bounded number of steps, dropping the oldest", () => {
    let history = NO_HISTORY;
    for (let index = 0; index < 60; index += 1) {
      history = remember(history, state(`role-${index}`), `structure-${index}`);
    }

    expect(history).toHaveLength(50);
    expect(history[0].state.definition.agents[0].role).toBe("role-10");
  });
});

describe("undoing", () => {
  it("gives back the newest state and the history without it", () => {
    let history = remember(NO_HISTORY, state("first"), "structure");
    history = remember(history, state("second"), "structure");

    const step = undo(history);

    expect(step?.state.definition.agents[0].role).toBe("second");
    expect(step?.history).toHaveLength(1);
  });

  it("says there is nothing to take back rather than inventing a state", () => {
    expect(undo(NO_HISTORY)).toBeNull();
  });

  it("carries the arrangement back with the definition", () => {
    // A move is an action like any other, so undoing one has to put the node back.
    const before = state("Scout", new Map([["agent-1", { x: 10, y: 20 }]]));
    const step = undo(remember(NO_HISTORY, before, "move:agent-1"));

    expect(step?.state.places.get("agent-1")).toEqual({ x: 10, y: 20 });
  });
});

describe("what kind of action a patch is", () => {
  it("calls a typed field typing, so a burst of it collapses", () => {
    expect(kindForPatch("agent-1", { prompt: "look" })).toBe("text:agent-1:prompt");
  });

  it("calls picking a model or a tool an action of its own", () => {
    // One click, one step back — there is nothing to collapse.
    expect(kindForPatch("agent-1", { modelId: "dear-one" })).toBe("agent:agent-1");
    expect(kindForPatch("agent-1", { tools: ["get_candles"] })).toBe("agent:agent-1");
  });
});
