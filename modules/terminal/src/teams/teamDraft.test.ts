import { describe, expect, it } from "vitest";
import {
  addAgent,
  addDependency,
  emptyDefinition,
  hasChanges,
  layout,
  nextAgentKey,
  removeAgent,
  removeDependency,
  updateAgent,
} from "./teamDraft";
import type { TeamDefinition } from "./teamsApi";

const MODEL = "a-model-the-module-published";

function three(): TeamDefinition {
  return {
    agents: [
      { key: "agent-1", role: "Scout", prompt: "", guidance: "", modelId: MODEL, tools: [] },
      { key: "agent-2", role: "Judge", prompt: "", guidance: "", modelId: MODEL, tools: [] },
      { key: "agent-3", role: "Writer", prompt: "", guidance: "", modelId: MODEL, tools: [] },
    ],
    dependencies: [
      { from: "agent-1", to: "agent-2" },
      { from: "agent-2", to: "agent-3" },
    ],
    limits: { runLimit: null, dailyLimit: null },
  };
}

describe("a new team", () => {
  it("starts with one agent on the model it was given", () => {
    const definition = emptyDefinition(MODEL);
    expect(definition.agents).toHaveLength(1);
    expect(definition.agents[0].modelId).toBe(MODEL);
    expect(definition.dependencies).toEqual([]);
  });
});

describe("agent keys", () => {
  it("skips the ones already taken rather than counting entries", () => {
    // Removing agent-2 and adding one back must not reuse a key an edge might still be
    // drawn against in the same session.
    const definition = removeAgent(three(), "agent-2");
    expect(nextAgentKey(definition)).toBe("agent-2");
  });
});

describe("removing an agent", () => {
  it("takes every dependency touching it with it", () => {
    const definition = removeAgent(three(), "agent-2");

    expect(definition.agents.map((agent) => agent.key)).toEqual(["agent-1", "agent-3"]);
    expect(definition.dependencies).toEqual([]);
  });
});

describe("dependencies", () => {
  it("adds one", () => {
    const definition = addDependency(three(), { from: "agent-1", to: "agent-3" });
    expect(definition.dependencies).toHaveLength(3);
  });

  it("ignores an agent depending on itself", () => {
    // A gesture, not an intention — and the module would refuse it, so there is no
    // reason to ask.
    expect(addDependency(three(), { from: "agent-1", to: "agent-1" })).toEqual(three());
  });

  it("ignores the same dependency drawn twice", () => {
    expect(addDependency(three(), { from: "agent-1", to: "agent-2" })).toEqual(three());
  });

  it("removes one by both its ends", () => {
    const definition = removeDependency(three(), { from: "agent-1", to: "agent-2" });
    expect(definition.dependencies).toEqual([{ from: "agent-2", to: "agent-3" }]);
  });
});

describe("editing an agent", () => {
  it("changes only the one named", () => {
    const definition = updateAgent(three(), "agent-2", { role: "Referee", tools: ["get_candles"] });

    expect(definition.agents[1]).toMatchObject({ role: "Referee", tools: ["get_candles"] });
    expect(definition.agents[0]).toEqual(three().agents[0]);
  });

  it("leaves the definition it was given untouched", () => {
    const before = three();
    addAgent(before, MODEL);
    expect(before.agents).toHaveLength(3);
  });
});

describe("unsaved changes", () => {
  it("are gone again when an edit is undone by hand", () => {
    const saved = three();
    const renamed = updateAgent(saved, "agent-1", { role: "Sentry" });
    expect(hasChanges(renamed, saved)).toBe(true);
    expect(hasChanges(updateAgent(renamed, "agent-1", { role: "Scout" }), saved)).toBe(false);
  });
});

describe("layout", () => {
  it("puts each agent one column past the ones it waits for", () => {
    const positions = layout(three());

    expect(positions.get("agent-1")!.x).toBe(0);
    expect(positions.get("agent-2")!.x).toBeGreaterThan(positions.get("agent-1")!.x);
    expect(positions.get("agent-3")!.x).toBeGreaterThan(positions.get("agent-2")!.x);
  });

  it("stacks agents that wait for nothing in the same column", () => {
    const definition: TeamDefinition = { ...three(), dependencies: [] };
    const positions = layout(definition);

    expect(new Set([...positions.values()].map((position) => position.x))).toEqual(new Set([0]));
    expect(new Set([...positions.values()].map((position) => position.y)).size).toBe(3);
  });

  it("still answers for a draft carrying a cycle", () => {
    // The module refuses one, but an operator can draw it on the way to noticing — and
    // a view that hangs while they do is worse than a view that puts the nodes anywhere.
    const definition: TeamDefinition = {
      ...three(),
      dependencies: [
        { from: "agent-1", to: "agent-2" },
        { from: "agent-2", to: "agent-1" },
      ],
    };

    expect(layout(definition).size).toBe(3);
  });
});
