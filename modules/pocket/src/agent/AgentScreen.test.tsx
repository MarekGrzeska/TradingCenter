import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AgentScreen } from "./AgentScreen";
import type { AgentApi, AgentMessage, AgentStreamEvent } from "./agentApi";
import { ArchiveError } from "../data/http";

const SESSION = { id: 7, title: "About the fed", currentModelId: "gpt-5", lastActiveAt: new Date() };
const OLDER = {
  id: 3,
  title: "Silver in March",
  currentModelId: "gpt-5",
  lastActiveAt: new Date("2026-08-20T10:00:00Z"),
};

async function* streamOf(...events: AgentStreamEvent[]): AsyncGenerator<AgentStreamEvent> {
  for (const event of events) yield event;
}

function reply(content: string, toolCalls: AgentMessage["toolCalls"] = []): AgentMessage {
  return {
    id: 2,
    role: "agent",
    content,
    incomplete: false,
    stopped: false,
    createdAt: new Date(),
    toolCalls,
  };
}

function anApi(overrides: Partial<AgentApi> = {}): AgentApi {
  return {
    listModels: vi.fn(async () => [{ id: "gpt-5", displayName: "GPT-5", costRank: 1 }]),
    listSessions: vi.fn(async () => [SESSION]),
    createSession: vi.fn(async () => SESSION),
    setModel: vi.fn(async () => SESSION),
    listMessages: vi.fn(async () => []),
    sendMessage: vi.fn(async () => streamOf({ kind: "complete", incomplete: false })),
    stop: vi.fn(async () => {}),
    ...overrides,
  };
}

describe("the agent screen", () => {
  it("sends what was typed and shows the tools the answer went through", async () => {
    const call = {
      roundIndex: 0,
      position: 0,
      name: "polymarket_search_markets",
      arguments: { query: "fed" },
      outcome: "ok" as const,
      resultText: "2 events",
      durationMs: 412,
      source: "server" as const,
    };
    const api = anApi({
      sendMessage: vi.fn(async () =>
        streamOf(
          { kind: "toolCall", call },
          { kind: "fragment", text: "Two markets price it." },
          { kind: "complete", incomplete: false },
        ),
      ),
      listMessages: vi
        .fn<AgentApi["listMessages"]>()
        .mockResolvedValueOnce([])
        .mockResolvedValue([reply("Two markets price it.", [call])]),
    });

    render(<AgentScreen api={api} />);
    await userEvent.type(await screen.findByPlaceholderText(/ask the agent/i), "what about the fed");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("Two markets price it.")).toBeInTheDocument();
    expect(api.sendMessage).toHaveBeenCalledWith(7, "what about the fed", expect.anything());
    // The point of the screen: which tool ran, and how it went.
    expect(screen.getByText("polymarket_search_markets")).toBeInTheDocument();
    expect(screen.getByText("ok")).toBeInTheDocument();
  });

  it("says the workbench cannot be reached rather than showing an empty conversation", async () => {
    const api = anApi({
      listSessions: vi.fn(async () => {
        throw new ArchiveError("unreachable", "workbench is not reachable");
      }),
    });

    render(<AgentScreen api={api} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("workbench is not reachable");
  });

  it("carries a refusal of the turn itself into the transcript", async () => {
    const api = anApi({
      sendMessage: vi.fn(async () => {
        throw new ArchiveError("refused", "this month's cost limit is spent");
      }),
    });

    render(<AgentScreen api={api} />);
    await userEvent.type(await screen.findByPlaceholderText(/ask the agent/i), "hello");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("this month's cost limit is spent");
  });

  it("opens a conversation from the history rather than starting over", async () => {
    const api = anApi({
      listSessions: vi.fn(async () => [SESSION, OLDER]),
      listMessages: vi.fn(async (id: number) =>
        id === OLDER.id ? [reply("Silver ended the week at 0.41.")] : [],
      ),
    });

    render(<AgentScreen api={api} />);
    await userEvent.click(await screen.findByRole("button", { name: "Conversations" }));
    await userEvent.click(screen.getByRole("button", { name: /silver in march/i }));

    expect(await screen.findByText("Silver ended the week at 0.41.")).toBeInTheDocument();
    expect(api.listMessages).toHaveBeenCalledWith(3, expect.anything());
  });

  it("starts a new conversation without creating one nobody has written in", async () => {
    const api = anApi({
      listSessions: vi.fn(async () => [SESSION]),
      listMessages: vi.fn(async () => [reply("An older answer.")]),
    });

    render(<AgentScreen api={api} />);
    expect(await screen.findByText("An older answer.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "New conversation" }));

    expect(screen.queryByText("An older answer.")).not.toBeInTheDocument();
    // The session is created by the first message, not by the tap: a conversation nobody said
    // anything in is a row in the history for the operator to scroll past.
    expect(api.createSession).not.toHaveBeenCalled();
  });
});
