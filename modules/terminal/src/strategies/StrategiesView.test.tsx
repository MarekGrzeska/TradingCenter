import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { createAgentActivityStore, type AgentActivityStore } from "../agent/agentActivity";
import type { AgentApi, AgentSession } from "../agent/agentApi";
import { createAgentChatStore, STORAGE_KEY } from "../agent/agentChatStore";
import type { DrawingsStore } from "../agent/drawingsStore";
import type { AgentStreamEvent } from "../agent/stream";
import { strategyInView } from "../agent/strategyInView";
import type { ArchiveAdmin } from "../data/source";
import { MarketDataError } from "../data/types";
import { StrategiesView } from "./StrategiesView";
import type { CostProfile, Revision, StrategiesApi, StrategyItem } from "./strategiesApi";

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
  conversationId: null,
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
    detail: vi.fn(async () => ({ item, revision: revision(4) })),
    revisions: vi.fn(async () => []),
    changes: vi.fn(async () => []),
    validate: vi.fn(async () => ({ valid: true, problems: [], summary: revision(4).summary })),
    create: vi.fn(),
    save: vi.fn(),
    setArchived: vi.fn(),
    setConversation: vi.fn(async () => {}),
    costs: vi.fn(async () => null),
    putCosts: vi.fn(),
    costsFromBroker: vi.fn(async () => BROKER),
    runs: vi.fn(async () => []),
    run: vi.fn(),
    trades: vi.fn(),
    enqueue: vi.fn(),
    cancel: vi.fn(),
    ...overrides,
  } as StrategiesApi;
}

const BROKER: CostProfile = {
  costs: { spread: 0.3, slippage: 0, overnight_long: 0.000151992, overnight_short: -0.000069792, rollover_hour: 21 },
  source: "broker",
  fetchedAt: new Date("2026-10-25T09:00:00Z"),
};

async function* answered(): AsyncGenerator<AgentStreamEvent> {
  yield { kind: "fragment", text: "Zapisałem." };
  yield { kind: "complete", incomplete: false };
}

/** Just enough of the agent module for a conversation to start, carry a turn and end it. */
function fakeAgent() {
  const sessions: AgentSession[] = [];
  const api = {
    listModels: vi.fn(async () => []),
    listSessions: vi.fn(async () => sessions),
    createSession: vi.fn(async () => {
      const session = { id: 42, title: null, currentModelId: "luna", createdAt: 0, lastActiveAt: 0 };
      sessions.push(session);
      return session;
    }),
    renameSession: vi.fn(async (id: number, title: string) => ({ ...sessions[0], id, title })),
    getMessages: vi.fn(async () => []),
    getUnclaimedToolCalls: vi.fn(async () => []),
    sendMessage: vi.fn(async () => answered()),
  } as unknown as AgentApi;
  return api;
}

const noDrawings = { refreshAll: async () => ({ added: 0, removed: 0 }) } as unknown as DrawingsStore;

function strategyChat(agent: AgentApi, activity: AgentActivityStore) {
  return createAgentChatStore(null, agent, async () => null, () => null, noDrawings, activity, strategyInView);
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

  it("sends from the strategy's own chat with the strategy on screen, and leaves the panel as it was", async () => {
    const activity = createAgentActivityStore();
    const agent = fakeAgent();
    const api = fakeApi();
    render(<StrategiesView api={api} pairs={pairs} activity={activity} chat={strategyChat(agent, activity)} />);
    await userEvent.click(await screen.findByRole("button", { name: /US100 pullback/ }));
    await screen.findByText(/rewizja 4/);

    const chat = screen.getByRole("complementary", { name: "Czat strategii" });
    await userEvent.type(within(chat).getByRole("textbox"), "Zaostrz stop{Enter}");

    await waitFor(() => expect(agent.sendMessage).toHaveBeenCalled());
    expect(vi.mocked(agent.sendMessage).mock.calls[0][4]).toEqual({ strategyId: 7, revision: 4, draft: null });
    // The conversation this chat started belongs to the strategy, under its name.
    await waitFor(() => expect(api.setConversation).toHaveBeenCalledWith(7, 42, expect.anything()));
    expect(agent.renameSession).toHaveBeenCalledWith(42, "US100 pullback", expect.anything());
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("gives a strategy the agent created from the chat the conversation it was created in", async () => {
    const activity = createAgentActivityStore();
    const agent = fakeAgent();
    const created: StrategyItem = { ...item, id: 8, name: "EURUSD breakout", changedAt: new Date("2026-10-25T11:00:00Z") };
    const api = fakeApi({
      strategies: vi.fn(async () => [item]),
      detail: vi.fn(async () => ({ item: created, revision: { ...revision(1, "EURUSD breakout"), strategyId: 8 } })),
    });
    render(<StrategiesView api={api} pairs={pairs} activity={activity} chat={strategyChat(agent, activity)} />);
    await userEvent.click(await screen.findByRole("button", { name: "Nowa…" }));

    vi.mocked(api.strategies).mockImplementation(async () => [item, created]);
    const chat = screen.getByRole("complementary", { name: "Czat strategii" });
    await userEvent.type(within(chat).getByRole("textbox"), "Wybicie z zakresu na EURUSD{Enter}");

    expect(await screen.findByText("Agent utworzył tę strategię.")).toBeInTheDocument();
    await waitFor(() => expect(api.setConversation).toHaveBeenCalledWith(8, 42, expect.anything()));
    expect(api.setConversation).toHaveBeenCalledTimes(1);
  });
});
