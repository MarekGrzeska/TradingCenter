import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AgentCostView } from "./AgentCostView";
import { createAgentChatStore } from "../agentChatStore";
import type { AgentApi, AgentUsageSummary, UsageRange } from "../agentApi";

function summaryFixture(overrides: Partial<AgentUsageSummary> = {}): AgentUsageSummary {
  return {
    totalCost: "1.2345",
    byModel: [],
    bySession: [],
    byDay: [],
    ...overrides,
  };
}

function fakeApi(overrides: Partial<AgentApi> = {}): AgentApi {
  return {
    listModels: async () => [],
    listSessions: async () => [],
    getSession: async () => {
      throw new Error("not used");
    },
    createSession: async () => {
      throw new Error("not used");
    },
    setSessionModel: async () => {
      throw new Error("not used");
    },
    getMessages: async () => [],
    sendMessage: async () => {
      throw new Error("not used");
    },
    usage: async () => summaryFixture(),
    ...overrides,
  };
}

describe("AgentCostView", () => {
  it("renders numbers straight from the module — tokens, cost and unknown count, untouched", async () => {
    const api = fakeApi({
      usage: async () =>
        summaryFixture({
          totalCost: "3.4500",
          byModel: [
            { key: "gpt-5.6-luna", inputTokens: 12_345, outputTokens: 6_789, cost: "1.2300", unknownCount: 0 },
          ],
          bySession: [],
          byDay: [
            { key: "2026-08-11", inputTokens: 555, outputTokens: 222, cost: "1.2300", unknownCount: 2 },
          ],
        }),
    });
    render(<AgentCostView api={api} />);

    await screen.findByText("$3.4500");
    expect(screen.getByText("gpt-5.6-luna")).toBeInTheDocument();
    expect(screen.getByText("12,345")).toBeInTheDocument();
    expect(screen.getByText("6,789")).toBeInTheDocument();
    // Cost is rendered as the module's own string with a `$` prefix — nothing here
    // parses it into a number, multiplies, or sums it with anything else.
    expect(screen.getAllByText("$1.2300")).toHaveLength(2);
    expect(screen.getByText("+2 unknown")).toBeInTheDocument();
    expect(screen.getByText("2026-08-11")).toBeInTheDocument();
  });

  it("says nothing was used, rather than an empty table with no explanation", async () => {
    render(<AgentCostView api={fakeApi()} />);
    await screen.findByText(/nothing was used in this range/i);
  });

  it("says the module is unreachable and does not show yesterday's numbers as current", async () => {
    const api = fakeApi({
      usage: async () => {
        throw new Error("agent is not reachable");
      },
    });
    render(<AgentCostView api={api} />);

    await screen.findByText(/agent module is not reachable/i);
    expect(screen.queryByText(/^\$/)).not.toBeInTheDocument();
  });

  it("recovers on retry once the module answers again", async () => {
    let fail = true;
    const api = fakeApi({
      usage: async () => {
        if (fail) throw new Error("agent is not reachable");
        return summaryFixture({
          totalCost: "9.9900",
          byModel: [{ key: "luna", inputTokens: 1, outputTokens: 1, cost: "0.5000", unknownCount: 0 }],
        });
      },
    });
    const user = userEvent.setup();
    render(<AgentCostView api={api} />);
    await screen.findByText(/agent module is not reachable/i);

    fail = false;
    await user.click(screen.getByRole("button", { name: /retry/i }));
    await screen.findByText("$9.9900");
    expect(screen.getByText("$0.5000")).toBeInTheDocument();
  });

  it("opens the conversation from its row, since the module publishes no per-call breakdown", async () => {
    const api = fakeApi({
      usage: async () =>
        summaryFixture({
          bySession: [{ key: "7", inputTokens: 100, outputTokens: 50, cost: "0.0100", unknownCount: 0 }],
        }),
    });
    const chatStore = createAgentChatStore(null, {
      ...fakeApi(),
      listSessions: async () => [
        { id: 7, title: "why is BTC flat", currentModelId: "luna", createdAt: 0, lastActiveAt: 0 },
      ],
    });
    const user = userEvent.setup();
    render(<AgentCostView api={api} chatStore={chatStore} />);

    await screen.findByText("#7");
    expect(chatStore.getSnapshot().expanded).toBe(false);

    await user.click(screen.getByRole("button", { name: /^open$/i }));

    expect(chatStore.getSnapshot().expanded).toBe(true);
    expect(chatStore.getSnapshot().activeSessionId).toBe(7);
  });

  it("changing the date range re-reads usage for the new range", async () => {
    const seen: UsageRange[] = [];
    const api = fakeApi({
      usage: async (range) => {
        seen.push(range);
        return summaryFixture();
      },
    });
    render(<AgentCostView api={api} />);
    await waitFor(() => expect(seen.length).toBeGreaterThan(0));
    const first = seen[0];

    // A native date input's own multi-segment editor is not something `userEvent.type`
    // models well; setting the whole value at once is how a picked date actually
    // arrives at the `onChange` handler.
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-01-01" } });

    await waitFor(() => expect(seen.length).toBeGreaterThan(1));
    const last = seen[seen.length - 1];
    expect(last.from).not.toBe(first.from);
  });
});
