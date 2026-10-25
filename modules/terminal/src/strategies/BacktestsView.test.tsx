import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { createAgentActivityStore } from "../agent/agentActivity";
import { MarketDataError } from "../data/types";
import { BacktestsView } from "./BacktestsView";
import { Refused, type ComparedRun, type RunItem, type StrategiesApi, type StrategyItem } from "./strategiesApi";

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

const compared = (runId: number, strategyId: number, totalR: number): ComparedRun => ({
  run_id: runId,
  strategy_id: strategyId,
  revision: 1,
  params: { stop: 2 },
  trades: 10,
  win_rate: 0.5,
  expectancy_r: 0.1,
  expectancy_pct: 0.001,
  total_r: totalR,
  return_pct: 0.01,
  profit_factor: 1.2,
  max_drawdown_r: 3,
  max_drawdown_pct: 0.05,
  worst_mae_pct: -0.02,
  sharpe: 1,
  sortino: 1,
  calmar: 1,
  longest_losing_streak: 4,
  total_r_without_best_5: 0.5,
  pessimistic_resolutions: 0,
});

async function tick(...ids: number[]) {
  for (const id of ids) await userEvent.click(await screen.findByRole("checkbox", { name: `Porównaj uruchomienie ${id}` }));
  await userEvent.click(screen.getByRole("button", { name: /Porównaj \(/ }));
}

function fakeApi(overrides: Partial<StrategiesApi> = {}): StrategiesApi {
  return {
    health: vi.fn(async () => ({ queued: 0, running: 0, maxExecutionBars: 1_500_000 })),
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

  it("puts two runs of different strategies side by side, a column each", async () => {
    const api = fakeApi({ compare: vi.fn(async () => [compared(11, 7, 1.5), compared(12, 8, -2)]) });
    view(api);
    await tick(11, 12);

    const table = await screen.findByRole("table", { name: "Porównanie" });
    expect(api.compare).toHaveBeenCalledWith([11, 12], expect.anything());
    expect(within(table).getByRole("columnheader", { name: /#12 · EURUSD breakout/ })).toBeInTheDocument();
    expect(within(table).getByRole("row", { name: /Suma/ })).toHaveTextContent("-2 R");
  });

  it("says every difference the package named instead of a table", async () => {
    const reason = "run 12 differs from run 11 in costs: spread";
    view(fakeApi({ compare: vi.fn(async () => Promise.reject(new Refused("no", [{ path: "run_id", message: reason, column: null, hint: null }]))) }));
    await tick(11, 12);

    expect(await screen.findByRole("alert")).toHaveTextContent(reason);
    expect(screen.queryByRole("table", { name: "Porównanie" })).toBeNull();
  });

  it("lets no run that has not finished be ticked", async () => {
    view(fakeApi({ runs: vi.fn(async () => [run(11, 7), { ...run(13, 7), status: "running" as const }]) }));

    expect(await screen.findByRole("checkbox", { name: "Porównaj uruchomienie 13" })).toBeDisabled();
  });
});
