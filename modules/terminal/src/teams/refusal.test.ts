import { describe, expect, it } from "vitest";
import { locateRefusal } from "./refusal";
import type { TeamDefinition } from "./teamsApi";

const definition: TeamDefinition = {
  agents: [
    { key: "agent-1", role: "Scout", prompt: "", guidance: "", modelId: "m", tools: [] },
    { key: "agent-2", role: "Judge", prompt: "", guidance: "", modelId: "m", tools: [] },
    { key: "agent-10", role: "Writer", prompt: "", guidance: "", modelId: "m", tools: [] },
  ],
  dependencies: [
    { from: "agent-1", to: "agent-2" },
    { from: "agent-2", to: "agent-1" },
    { from: "agent-2", to: "agent-10" },
  ],
  limits: { runLimit: null, dailyLimit: null },
  trading: { maxOrderSize: null, ordersPerRun: null, ordersPerDay: null },
};

describe("locating a refusal", () => {
  it("finds the agent a model refusal names", () => {
    const refusal = locateRefusal(
      "agent 'agent-2' names model 'gpt-9-imaginary', which is not in this module's model catalogue",
      definition,
    );

    expect(refusal.agents).toEqual(["agent-2"]);
    expect(refusal.dependencies).toEqual([]);
  });

  it("finds the dependencies a cycle runs through", () => {
    // The scenario `terminal-teams` names: the module refuses, and the terminal has to
    // point at the dependency it refused over rather than at the whole canvas.
    const refusal = locateRefusal(
      "Value error, dependency cycle involving: ['agent-1', 'agent-2']",
      definition,
    );

    expect(refusal.agents).toEqual(["agent-1", "agent-2"]);
    expect(refusal.dependencies).toEqual([
      { from: "agent-1", to: "agent-2" },
      { from: "agent-2", to: "agent-1" },
    ]);
  });

  it("does not read agent-1 out of a message about agent-10", () => {
    const refusal = locateRefusal(
      "agent(s) with no dependency in either direction: ['agent-10']",
      definition,
    );

    expect(refusal.agents).toEqual(["agent-10"]);
  });

  it("keeps a message naming nothing it recognises, rather than replacing it", () => {
    const refusal = locateRefusal("a team needs at least one agent", definition);

    expect(refusal.agents).toEqual([]);
    expect(refusal.message).toBe("a team needs at least one agent");
  });

  it("marks an edge only when both its ends are named", () => {
    const refusal = locateRefusal("agent 'agent-2' names no model", definition);

    expect(refusal.dependencies).toEqual([]);
  });
});
