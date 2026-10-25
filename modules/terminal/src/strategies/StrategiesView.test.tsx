import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { createAgentActivityStore } from "../agent/agentActivity";
import { strategyInView } from "../agent/strategyInView";
import type { ArchiveAdmin } from "../data/source";
import { MarketDataError } from "../data/types";
import { StrategiesView } from "./StrategiesView";
import type { Revision, StrategiesApi, StrategyItem } from "./strategiesApi";

/**
 * The tab from the operator's seat: a strategy opens with its summary, an absent package says which setting enables it,
 * and a revision the agent saves after a turn replaces the editor's text only when nothing there is unsaved.
 */

const DOCUMENT = { schema: 1, name: "US100 pullback", symbol: "US100", timeframe: "HOUR", params: {} };

const item: StrategyItem = {
  id: 7,
  name: "US100 pullback",
  symbol: "US100",
  timeframe: "HOUR_4",
  latestRevision: 4,
  latestAuthor: "agent",
  changedAt: new Date("2026-10-25T10:00:00Z"),
  createdAt: new Date("2026-10-24T10:00:00Z"),
  archivedAt: null,
  trials: 3,
};

const revision = (n: number, name = "US100 pullback"): Revision => ({
  strategyId: 7,
  n,
  document: { ...DOCUMENT, name },
  author: "agent",
  createdAt: new Date("2026-10-25T10:00:00Z"),
  summary: { name, sections: [{ title: "Instrument", lines: ["US100, decyzje na zamknięciu świecy h1."] }], hypothesis: "", notes: "" },
});

function fakeApi(overrides: Partial<StrategiesApi> = {}): StrategiesApi {
  return {
    health: vi.fn(async () => ({ queued: 0, running: 0, maxMinuteBars: 1_500_000 })),
    language: vi.fn(async () => ({
      schema_version: 1,
      sections: [],
      constructions: [],
      series: {},
      time: {},
      constants: {},
      position: {},
      history: {},
      resolutions: [],
      functions: [],
      indicators: [],
      max_bars: 5000,
    })),
    strategies: vi.fn(async () => [item]),
    revision: vi.fn(async (_id: number, n: number | null) => revision(n ?? 4)),
    revisions: vi.fn(async () => []),
    changes: vi.fn(async () => []),
    validate: vi.fn(async () => ({ valid: true, problems: [], summary: revision(4).summary })),
    create: vi.fn(),
    save: vi.fn(),
    setArchived: vi.fn(),
    costs: vi.fn(async () => null),
    putCosts: vi.fn(),
    runs: vi.fn(async () => []),
    run: vi.fn(),
    trades: vi.fn(),
    enqueue: vi.fn(),
    cancel: vi.fn(),
    ...overrides,
  } as StrategiesApi;
}

const pairs = { listPairs: vi.fn(async () => []) } as unknown as ArchiveAdmin;

describe("StrategiesView", () => {
  it("lists a strategy in the terminal's interval names and opens it with its summary", async () => {
    render(<StrategiesView api={fakeApi()} pairs={pairs} activity={createAgentActivityStore()} />);

    const entry = await screen.findByRole("button", { name: /US100 pullback/ });
    expect(entry).toHaveTextContent("h4");
    expect(entry).not.toHaveTextContent("HOUR_4");
    await userEvent.click(entry);

    expect(await screen.findByText("US100, decyzje na zamknięciu świecy h1.")).toBeInTheDocument();
    expect(strategyInView()).toEqual({ strategyId: 7, revision: 4, draft: null });
  });

  it("names the setting when the workbench has no strategies package", async () => {
    const absent = fakeApi({
      health: vi.fn(async () => {
        throw new MarketDataError("not-found", "Not Found");
      }),
    });
    render(<StrategiesView api={absent} pairs={pairs} activity={createAgentActivityStore()} />);

    expect(await screen.findByText("STRATEGIES_DATABASE_URL")).toBeInTheDocument();
  });

  it("takes the agent's revision after a turn, and says the agent saved it", async () => {
    const activity = createAgentActivityStore();
    const api = fakeApi();
    render(<StrategiesView api={api} pairs={pairs} activity={activity} />);
    await userEvent.click(await screen.findByRole("button", { name: /US100 pullback/ }));
    await screen.findByText(/rewizja 4/);

    vi.mocked(api.revision).mockImplementation(async () => revision(5, "with a tighter stop"));
    activity.turnFinished();

    expect(await screen.findByText("Agent zapisał rewizję 5.")).toBeInTheDocument();
    await waitFor(() => expect(strategyInView()).toEqual({ strategyId: 7, revision: 5, draft: null }));
  });
});
