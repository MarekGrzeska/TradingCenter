import { describe, expect, it } from "vitest";
import { filterRuns, groupStrategies, NO_RUN_FILTER, nextSort, shortName, sortRuns, timeframesOf, trials } from "./order";
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
          annualReturnPct: null,
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

  it("keeps one interval, and offers the intervals from the shortest", () => {
    const items = [
      strategy(1, "US100 H1 — cofnięcie do EMA", "HOUR", "2026-10-01T00:00:00Z"),
      strategy(2, "US100 M5 — ORB 15 min", "MINUTE_5", "2026-10-01T00:00:00Z"),
    ];

    expect(groupStrategies(items, "", "HOUR").map((g) => g.timeframe)).toEqual(["HOUR"]);
    expect(groupStrategies(items, "orb", "HOUR")).toHaveLength(0);
    expect(timeframesOf(items)).toEqual(["MINUTE_5", "HOUR"]);
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

describe("filterRuns", () => {
  const strategies = [
    strategy(1, "US100 H1 — cofnięcie do EMA", "HOUR", "2026-10-01T00:00:00Z"),
    strategy(2, "US100 M5 — ORB 15 min", "MINUTE_5", "2026-10-01T00:00:00Z"),
  ];
  const of = (id: number, strategyId: number, sharpe: number | null, annual: number | null, from: string, to: string): RunItem => {
    const base = run(id, sharpe);
    return {
      ...base,
      strategyId,
      from: new Date(from),
      to: new Date(to),
      headline: base.headline && { ...base.headline, annualReturnPct: annual },
    };
  };
  const runs = [
    of(1, 1, 1.5, 0.3, "2025-01-01T00:00:00Z", "2025-12-31T00:00:00Z"),
    of(2, 2, 0.4, -0.1, "2024-01-01T00:00:00Z", "2026-06-30T00:00:00Z"),
    of(3, 2, null, null, "2025-03-01T00:00:00Z", "2025-04-01T00:00:00Z"),
  ];
  const ids = (filter: Partial<typeof NO_RUN_FILTER>) => filterRuns(runs, { ...NO_RUN_FILTER, ...filter }, strategies).map((r) => r.id);

  it("narrows by the strategy's name and interval", () => {
    expect(ids({})).toEqual([1, 2, 3]);
    expect(ids({ name: "orb" })).toEqual([2, 3]);
    expect(ids({ timeframe: "HOUR" })).toEqual([1]);
  });

  it("keeps a run whose tested range lies within the days given", () => {
    expect(ids({ from: "2025-01-01" })).toEqual([1, 3]);
    expect(ids({ from: "2025-01-01", to: "2025-06-30" })).toEqual([3]);
  });

  it("takes minimums in percent and Polish decimals, and drops a run with no number in that column", () => {
    expect(ids({ minSharpe: "0,5" })).toEqual([1]);
    expect(ids({ minAnnualReturnPct: "-20" })).toEqual([1, 2]);
    expect(ids({ minAnnualReturnPct: "10" })).toEqual([1]);
    expect(ids({ minSharpe: "abc" })).toEqual([1, 2, 3]);
  });
});
