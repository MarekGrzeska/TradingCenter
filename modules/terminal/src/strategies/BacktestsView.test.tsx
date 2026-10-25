import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { createAgentActivityStore } from "../agent/agentActivity";
import { MarketDataError } from "../data/types";
import { BacktestsView } from "./BacktestsView";
import type { RunItem, StrategiesApi, StrategyItem } from "./strategiesApi";

/** The Backtests tab from the operator's seat: runs of every strategy by name, the form of the one picked, and an absent package. */

const strategy = (id: number, name: string): StrategyItem => ({
  id,
  name,
  symbol: "US100",
  timeframe: "HOUR",
  latestRevision: 1,
  latestAuthor: "agent",
  changedAt: new Date("2026-10-25T10:00:00Z"),
  createdAt: new Date("2026-10-25T10:00:00Z"),
  archivedAt: null,
  trials: 1,
  conversationId: null,
});

const run = (id: number, strategyId: number): RunItem => ({
  id,
  strategyId,
  revision: 1,
  status: "done",
  reason: null,
  requestedBy: "operator",
  from: new Date("2026-01-01T00:00:00Z"),
  to: new Date("2026-02-01T00:00:00Z"),
  queuedAt: new Date("2026-10-25T10:00:00Z"),
  headline: null,
});

function fakeApi(overrides: Partial<StrategiesApi> = {}): StrategiesApi {
  return {
    health: vi.fn(async () => ({ queued: 0, running: 0, maxMinuteBars: 1_500_000 })),
    strategies: vi.fn(async () => [strategy(7, "US100 pullback"), strategy(8, "EURUSD breakout")]),
    detail: vi.fn(async () => ({
      item: strategy(7, "US100 pullback"),
      revision: { strategyId: 7, n: 1, document: { symbol: "US100", params: {} }, author: "agent", createdAt: new Date(), summary: null },
    })),
    runs: vi.fn(async () => [run(11, 7), run(12, 8)]),
    costs: vi.fn(async () => null),
    costsFromBroker: vi.fn(async () => Promise.reject(new Error("down"))),
    ...overrides,
  } as unknown as StrategiesApi;
}

function view(api: StrategiesApi, url = "/backtests") {
  render(
    <MemoryRouter initialEntries={[url]}>
      <BacktestsView api={api} activity={createAgentActivityStore()} />
    </MemoryRouter>,
  );
}

describe("BacktestsView", () => {
  it("lists the runs of every strategy under its name", async () => {
    const api = fakeApi();
    view(api);

    expect(await screen.findByRole("cell", { name: "EURUSD breakout" })).toBeInTheDocument();
    expect(api.runs).toHaveBeenCalledWith(null, expect.anything());
    expect(screen.queryByRole("form", { name: "Uruchomienie" })).toBeNull();
  });

  it("opens with the strategy the Strategies tab sent, and its run form", async () => {
    const api = fakeApi();
    view(api, "/backtests?strategy=7");

    expect(await screen.findByRole("form", { name: "Uruchomienie" })).toBeInTheDocument();
    expect(api.runs).toHaveBeenCalledWith(7, expect.anything());
  });

  it("names the setting when the workbench has no strategies package", async () => {
    view(fakeApi({ health: vi.fn(async () => Promise.reject(new MarketDataError("not-found", "Not Found"))) }));

    expect(await screen.findByText("STRATEGIES_DATABASE_URL")).toBeInTheDocument();
  });
});
