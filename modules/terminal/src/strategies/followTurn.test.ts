import { describe, expect, it } from "vitest";
import { afterTurn, createdDuringTurn } from "./followTurn";
import type { StrategyItem } from "./strategiesApi";

const item = (id: number, author: "agent" | "operator", changedAt: number): StrategyItem => ({
  id,
  name: `s${id}`,
  symbol: "US100",
  timeframe: "HOUR",
  latestRevision: 1,
  latestAuthor: author,
  changedAt: new Date(changedAt),
  createdAt: new Date(changedAt),
  archivedAt: null,
  trials: 0,
});

describe("afterTurn", () => {
  it("loads the agent's revision when nothing is unsaved, and keeps the operator's text when something is", () => {
    expect(afterTurn({ strategyId: 7, base: 4, dirty: false }, 5)).toEqual({ kind: "load", revision: 5 });
    expect(afterTurn({ strategyId: 7, base: 4, dirty: true }, 5)).toEqual({ kind: "newer", revision: 5 });
    expect(afterTurn({ strategyId: 7, base: 5, dirty: false }, 5)).toEqual({ kind: "none" });
  });
});

describe("createdDuringTurn", () => {
  it("opens the strategy the agent created when none was open, and nothing when one was", () => {
    const now = [item(1, "operator", 1), item(2, "agent", 3), item(3, "agent", 2)];

    expect(createdDuringTurn(new Set([1]), now, false)).toBe(2);
    expect(createdDuringTurn(new Set([1]), now, true)).toBeNull();
    expect(createdDuringTurn(new Set([1, 2, 3]), now, false)).toBeNull();
  });
});
