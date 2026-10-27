import { describe, expect, it } from "vitest";
import { groupStrategies, nextSort, shortName, sortRuns, trials } from "./order";
import type { RunItem, StrategyItem } from "./strategiesApi";

const strategy = (id: number, name: string, timeframe: string, changed: string): StrategyItem => ({
  id,
  name,
  symbol: "US100",
  timeframe,
  latestRevision: 1,
  latestAuthor: "agent",
  changedAt: new Date(changed),
  createdAt: new Date(changed),
  archivedAt: null,
  trials: 0,
  conversationId: null,
});

const run = (id: number, sharpe: number | null): RunItem => ({
  id,
  strategyId: 1,
  revision: 1,
  status: "done",
  reason: null,
  requestedBy: "agent",
  from: new Date("2026-01-01T00:00:00Z"),
  to: new Date("2026-02-01T00:00:00Z"),
  queuedAt: new Date("2026-02-01T00:00:00Z"),
  headline:
    sharpe === null
      ? null
      : {
          trades: 1,
          totalR: null,
          expectancyR: null,
          maxDrawdownR: null,
          sharpe,
          returnPct: null,
          costsSource: "broker",
          withoutCosts: false,
        },
});

describe("groupStrategies", () => {
  it("groups by interval from the shortest, the last changed first, and filters by name", () => {
    const groups = groupStrategies([
      strategy(1, "US100 H1 — cofnięcie do EMA", "HOUR", "2026-10-01T00:00:00Z"),
      strategy(2, "US100 M5 — ORB 15 min", "MINUTE_5", "2026-10-01T00:00:00Z"),
      strategy(3, "US100 M5 — luka otwarcia", "MINUTE_5", "2026-10-02T00:00:00Z"),
    ]);

    expect(groups.map((g) => g.timeframe)).toEqual(["MINUTE_5", "HOUR"]);
    expect(groups[0].strategies.map((s) => s.shortName)).toEqual(["luka otwarcia", "ORB 15 min"]);
    expect(groupStrategies([strategy(2, "US100 M5 — ORB 15 min", "MINUTE_5", "2026-10-01T00:00:00Z")], "orb")).toHaveLength(1);
    expect(groupStrategies([strategy(2, "US100 M5 — ORB 15 min", "MINUTE_5", "2026-10-01T00:00:00Z")], "ema")).toHaveLength(0);
  });

  it("keeps a name that says nothing but the group", () => {
    expect(shortName(strategy(1, "US100 pullback", "HOUR_4", "2026-10-01T00:00:00Z"))).toBe("US100 pullback");
  });
});

describe("trials", () => {
  it.each([
    [1, "1 próba"],
    [3, "3 próby"],
    [5, "5 prób"],
    [12, "12 prób"],
    [22, "22 próby"],
  ])("counts %i the Polish way", (count, said) => {
    expect(trials(count)).toBe(said);
  });
});

describe("sortRuns", () => {
  it("turns a column both ways and keeps runs without a number last", () => {
    const runs = [run(1, 0.5), run(2, null), run(3, 1.2)];
    const descending = nextSort(null, "sharpe");

    expect(sortRuns(runs, descending).map((r) => r.id)).toEqual([3, 1, 2]);
    expect(sortRuns(runs, nextSort(descending, "sharpe")).map((r) => r.id)).toEqual([1, 3, 2]);
  });
});
