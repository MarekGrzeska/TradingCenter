import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AgentChat } from "./AgentChat";
import { createAgentChatStore, STORAGE_KEY } from "./agentChatStore";
import type { AgentApi, AgentMessage, AgentModel, AgentSession, AgentToolCall } from "./agentApi";
import type { AgentStreamEvent } from "./stream";

function toolCall(overrides: Partial<AgentToolCall> = {}): AgentToolCall {
  return {
    roundIndex: 0,
    position: 0,
    name: "get_candles",
    arguments: { symbol: "US100", resolution: "DAY" },
    outcome: "ok",
    resultText: '{"candles": 78}',
    durationMs: 240,
    ...overrides,
  };
}

const MODELS: AgentModel[] = [
  { id: "luna", displayName: "Luna", costRank: 1, inputRatePer1M: "0.2", outputRatePer1M: "1.2" },
  { id: "sol", displayName: "Sol", costRank: 3, inputRatePer1M: "5", outputRatePer1M: "30" },
];

async function* fromArray(events: AgentStreamEvent[]): AsyncGenerator<AgentStreamEvent> {
  yield* events;
}

/** Suspends between events instead of resolving them all in one microtask sweep, so a
 *  test can observe the panel mid-turn without racing the code under test — same
 *  reasoning as `agentChatStore.test.ts`'s helper of the same shape. */
function controllableEvents() {
  let notify: (() => void) | null = null;
  const pending: AgentStreamEvent[] = [];

  async function* generator(): AsyncGenerator<AgentStreamEvent> {
    while (true) {
      if (pending.length > 0) {
        yield pending.shift()!;
        continue;
      }
      await new Promise<void>((resolve) => {
        notify = resolve;
      });
    }
  }

  return {
    events: generator(),
    push(event: AgentStreamEvent) {
      pending.push(event);
      notify?.();
      notify = null;
    },
  };
}

interface FakeApi extends AgentApi {
  sessions: AgentSession[];
  transcripts: Map<number, AgentMessage[]>;
  nextId: number;
  seed(title: string, modelId: string, messages?: AgentMessage[]): AgentSession;
  /** What the module itself would have persisted for a turn — the same write
   *  `sendMessage` does by default, exposed so a test overriding `sendMessage` for
   *  control over event *timing* does not also have to reinvent what ends up on
   *  reload, which is what a `finishTurn` reload always reflects. */
  recordExchange(
    id: number,
    content: string,
    replyText: string,
    incomplete: boolean,
    toolCalls?: AgentToolCall[],
  ): void;
}

function createFakeApi(): FakeApi {
  const api: FakeApi = {
    sessions: [],
    transcripts: new Map(),
    nextId: 1,

    seed(title, modelId, messages = []) {
      const session: AgentSession = {
        id: api.nextId++,
        title,
        currentModelId: modelId,
        createdAt: 0,
        lastActiveAt: 0,
      };
      api.sessions.push(session);
      api.transcripts.set(session.id, messages);
      return session;
    },

    async listModels() {
      return MODELS;
    },
    async listSessions() {
      return api.sessions.filter((s) => s.title !== null);
    },
    async getSession(id) {
      const found = api.sessions.find((s) => s.id === id);
      if (!found) throw new Error("no such session");
      return found;
    },
    async createSession(modelId) {
      const session: AgentSession = {
        id: api.nextId++,
        title: null,
        currentModelId: modelId ?? MODELS[0].id,
        createdAt: 0,
        lastActiveAt: 0,
      };
      api.sessions.push(session);
      api.transcripts.set(session.id, []);
      return session;
    },
    async setSessionModel(id, modelId) {
      const found = api.sessions.find((s) => s.id === id);
      if (!found) throw new Error("no such session");
      found.currentModelId = modelId;
      return found;
    },
    async renameSession(id, title) {
      const found = api.sessions.find((s) => s.id === id);
      if (!found) throw new Error("no such session");
      found.title = title;
      return found;
    },
    async deleteSession(id) {
      const index = api.sessions.findIndex((s) => s.id === id);
      if (index === -1) throw new Error("no such session");
      api.sessions.splice(index, 1);
      api.transcripts.delete(id);
    },
    async getMessages(id) {
      return api.transcripts.get(id) ?? [];
    },
    recordExchange(id, content, replyText, incomplete, toolCalls = []) {
      const transcript = api.transcripts.get(id) ?? [];
      transcript.push({
        id: transcript.length + 1,
        role: "operator",
        content,
        modelId: null,
        promptVersion: null,
        incomplete: false,
        createdAt: 0,
        toolCalls: [],
      });
      const session = api.sessions.find((s) => s.id === id);
      if (session && session.title === null) session.title = content.slice(0, 40);
      transcript.push({
        id: transcript.length + 1,
        role: "agent",
        content: replyText,
        modelId: session?.currentModelId ?? null,
        promptVersion: "v1",
        incomplete,
        createdAt: 0,
        toolCalls,
      });
      api.transcripts.set(id, transcript);
    },

    async sendMessage(id, content) {
      const replyText = `you asked: ${content}`;
      api.recordExchange(id, content, replyText, false);
      return fromArray([{ kind: "fragment", text: replyText }, { kind: "complete", incomplete: false }]);
    },
    async usage() {
      return { totalCost: "0", byModel: [], bySession: [], byDay: [] };
    },
    async getPrompt() {
      throw new Error("not used");
    },
    async updatePrompt() {
      throw new Error("not used");
    },
  };
  return api;
}

function memoryStorage(): Storage {
  const entries = new Map<string, string>();
  return {
    getItem: (key) => entries.get(key) ?? null,
    setItem: (key, value) => void entries.set(key, String(value)),
    removeItem: (key) => void entries.delete(key),
    clear: () => entries.clear(),
    key: (index) => [...entries.keys()][index] ?? null,
    get length() {
      return entries.size;
    },
  };
}

function renderChat(api: FakeApi = createFakeApi(), storage: Storage | null = null) {
  const store = createAgentChatStore(storage, api);
  return { api, store, ...render(<AgentChat store={store} />) };
}

describe("AgentChat", () => {
  it("starts collapsed, offering the rail and nothing else", () => {
    renderChat();

    expect(screen.getByRole("button", { name: /open agent chat/i })).toBeInTheDocument();
    expect(screen.queryByRole("complementary", { name: /agent chat/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /message the agent/i })).not.toBeInTheDocument();
  });

  it("expands from the rail, loads the catalogue, and collapses back to it", async () => {
    const user = userEvent.setup();
    renderChat();

    await user.click(screen.getByRole("button", { name: /open agent chat/i }));

    expect(screen.getByRole("complementary", { name: /agent chat/i })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /message the agent/i })).toBeInTheDocument();
    await screen.findByRole("option", { name: /luna/i });
    expect(screen.queryByText(/mockup/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /collapse agent chat/i }));
    expect(screen.getByRole("button", { name: /open agent chat/i })).toBeInTheDocument();
    expect(screen.queryByRole("complementary", { name: /agent chat/i })).not.toBeInTheDocument();
  });

  it("shows the model catalogue with its cost difference, never a list the terminal invented", async () => {
    const user = userEvent.setup();
    renderChat();
    await user.click(screen.getByRole("button", { name: /open agent chat/i }));

    const select = await screen.findByLabelText("Model");
    // The rates the module published, rendered as they arrived: per million, which is
    // what `agent/contract.py` now sends, and never rescaled here.
    expect(screen.getByRole("option", { name: /luna.*0\.2.*1\.2.*per 1M/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /sol.*5.*30.*per 1M/i })).toBeInTheDocument();

    await user.selectOptions(select, "sol");
    expect(select).toHaveValue("sol");
  });

  it("says the model picker is unavailable when the catalogue cannot be read, and offers no select", async () => {
    const api = createFakeApi();
    api.listModels = async () => {
      throw new Error("models unreachable");
    };
    const user = userEvent.setup();
    renderChat(api);
    await user.click(screen.getByRole("button", { name: /open agent chat/i }));

    await screen.findByText(/model picker unavailable/i);
    expect(screen.queryByLabelText("Model")).not.toBeInTheDocument();
  });

  it("shows waiting before the first fragment, streams the reply in, then settles it into the transcript", async () => {
    const api = createFakeApi();
    const controllable = controllableEvents();
    api.sendMessage = async (id, content) => {
      // Same write the module ends up doing — only the pacing of the events is
      // under this test's control, not what a reload afterwards would show.
      api.recordExchange(id, content, "consolidating", false);
      return controllable.events;
    };
    const user = userEvent.setup();
    renderChat(api);
    await user.click(screen.getByRole("button", { name: /open agent chat/i }));
    await screen.findByLabelText("Model");

    const box = screen.getByRole("textbox", { name: /message the agent/i });
    await user.type(box, "why is BTC flat");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(screen.getByText("why is BTC flat")).toBeInTheDocument();
    expect(box).toHaveValue("");
    await screen.findByText("thinking…");

    controllable.push({ kind: "fragment", text: "consolidating" });
    await screen.findByText("consolidating");

    controllable.push({ kind: "complete", incomplete: false });
    await waitFor(() => expect(screen.queryByText("thinking…")).not.toBeInTheDocument());
    // Settled from the module's own reload, not from what streamed — the same text
    // here either way, which is the point: nothing downstream can tell the two apart.
    await screen.findByText("consolidating");
  });

  it("shows a tool call as it happens, before the reply has said anything", async () => {
    const api = createFakeApi();
    const controllable = controllableEvents();
    api.sendMessage = async (id, content) => {
      api.recordExchange(id, content, "it rose 0.6%", false, [toolCall()]);
      return controllable.events;
    };
    const user = userEvent.setup();
    renderChat(api);
    await user.click(screen.getByRole("button", { name: /open agent chat/i }));
    await screen.findByLabelText("Model");

    const box = screen.getByRole("textbox", { name: /message the agent/i });
    await user.type(box, "summarise US100{Enter}");
    await screen.findByText("thinking…");

    controllable.push({ kind: "toolCall", call: toolCall() });

    await screen.findByText("get_candles");
    expect(screen.getByText("240 ms")).toBeInTheDocument();
    // The panel is still waiting on the model — a call resolving is not the reply
    // starting.
    expect(screen.getByText("thinking…")).toBeInTheDocument();

    controllable.push({ kind: "fragment", text: "it rose 0.6%" });
    controllable.push({ kind: "complete", incomplete: false });
    // Still there after the reload, now from the transcript rather than the stream.
    await screen.findByText("it rose 0.6%");
    expect(screen.getByText("get_candles")).toBeInTheDocument();
  });

  it("keeps a call's arguments and result behind one click", async () => {
    const api = createFakeApi();
    const session = api.seed("older chat", "luna");
    api.recordExchange(session.id, "summarise US100", "it rose 0.6%", false, [toolCall()]);
    const user = userEvent.setup();
    renderChat(api);
    await user.click(screen.getByRole("button", { name: /open agent chat/i }));
    await screen.findByLabelText("Model");
    await user.click(screen.getByRole("button", { name: /^conversations$/i }));
    await user.click(await screen.findByRole("button", { name: /^older chat$/i }));

    await screen.findByText("get_candles");
    // Collapsed by default: a turn is allowed eight calls, and eight open results would
    // bury the rozmowa they were made for.
    expect(screen.queryByText(/"symbol":"US100"/)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /expand get_candles/i }));

    expect(screen.getByText(/"symbol":"US100"/)).toBeInTheDocument();
    expect(screen.getByText('{"candles": 78}')).toBeInTheDocument();
  });

  it("tells a refusal, an unreachable server and a successful call apart", async () => {
    const api = createFakeApi();
    const session = api.seed("older chat", "luna");
    api.recordExchange(session.id, "summarise US100", "I could not check all of it", false, [
      toolCall(),
      toolCall({ position: 1, name: "summarize_range", outcome: "refused", durationMs: 18 }),
      toolCall({ position: 2, name: "describe_coverage", outcome: "unavailable", durationMs: 3 }),
    ]);
    const user = userEvent.setup();
    renderChat(api);
    await user.click(screen.getByRole("button", { name: /open agent chat/i }));
    await screen.findByLabelText("Model");
    await user.click(screen.getByRole("button", { name: /^conversations$/i }));
    await user.click(await screen.findByRole("button", { name: /^older chat$/i }));

    await screen.findByText("get_candles");
    expect(screen.getByText("ok")).toHaveClass("text-ink-muted");
    // A refusal is the archive answering "not like that"; an unreachable server means
    // nothing was asked and nothing is known. Reading the second as the first is how
    // "the archive has no data" gets said about data the archive has.
    expect(screen.getByText("refused")).toHaveClass("text-warning");
    expect(screen.getByText("no answer")).toHaveClass("text-critical");
    // And none of it makes the reply itself incomplete.
    expect(screen.queryByText(/incomplete/i)).not.toBeInTheDocument();
  });

  it("shows no entries for a turn that asked for nothing", async () => {
    const api = createFakeApi();
    const session = api.seed("older chat", "luna");
    api.recordExchange(session.id, "hello", "hello back", false);
    const user = userEvent.setup();
    renderChat(api);
    await user.click(screen.getByRole("button", { name: /open agent chat/i }));
    await screen.findByLabelText("Model");
    await user.click(screen.getByRole("button", { name: /^conversations$/i }));
    await user.click(await screen.findByRole("button", { name: /^older chat$/i }));

    await screen.findByText("hello back");
    expect(screen.queryByRole("button", { name: /expand /i })).not.toBeInTheDocument();
  });

  it("marks a broken reply as incomplete on the bubble itself, and keeps what arrived", async () => {
    const api = createFakeApi();
    api.sendMessage = async (id, content) => {
      api.recordExchange(id, content, "consolid", true);
      return fromArray([
        { kind: "fragment", text: "consolid" },
        { kind: "error", message: "the model call failed" },
      ]);
    };
    const user = userEvent.setup();
    renderChat(api);
    await user.click(screen.getByRole("button", { name: /open agent chat/i }));
    await screen.findByLabelText("Model");

    const box = screen.getByRole("textbox", { name: /message the agent/i });
    await user.type(box, "why is BTC flat{Enter}");

    await screen.findByText(/incomplete/i);
  });

  it("says the module is unreachable and shows no reply bubble when nothing was accepted", async () => {
    const api = createFakeApi();
    api.createSession = async () => {
      throw new Error("agent is not reachable");
    };
    const user = userEvent.setup();
    renderChat(api);
    await user.click(screen.getByRole("button", { name: /open agent chat/i }));
    await screen.findByLabelText("Model");

    const box = screen.getByRole("textbox", { name: /message the agent/i });
    await user.type(box, "why is BTC flat{Enter}");

    await screen.findByText(/agent module is not reachable/i);
    // The operator's own line is on screen; nothing pretending to be a reply is.
    expect(screen.getByText("why is BTC flat")).toBeInTheDocument();
    expect(screen.queryByText("thinking…")).not.toBeInTheDocument();
  });

  it("opens a past conversation from the list and loads its transcript from the module", async () => {
    const api = createFakeApi();
    api.seed("older chat", "luna", [
      {
        id: 1,
        role: "operator",
        content: "hello from before",
        modelId: null,
        promptVersion: null,
        incomplete: false,
        createdAt: 0,
        toolCalls: [],
      },
    ]);
    const user = userEvent.setup();
    renderChat(api);
    await user.click(screen.getByRole("button", { name: /open agent chat/i }));
    await screen.findByLabelText("Model");

    await user.click(screen.getByRole("button", { name: /^conversations$/i }));
    await user.click(await screen.findByRole("button", { name: /^older chat$/i }));

    await screen.findByText("hello from before");
    expect(screen.getByRole("textbox", { name: /message the agent/i })).toBeInTheDocument();
  });

  it("starts a new conversation empty, and it only joins the list after the first exchange", async () => {
    const api = createFakeApi();
    api.seed("older chat", "luna");
    const user = userEvent.setup();
    renderChat(api);
    await user.click(screen.getByRole("button", { name: /open agent chat/i }));
    await screen.findByLabelText("Model");

    await user.click(screen.getByRole("button", { name: /^conversations$/i }));
    await screen.findByRole("button", { name: /^older chat$/i });
    await user.click(screen.getByRole("button", { name: /^back to chat$/i }));

    await user.click(screen.getByRole("button", { name: /^new$/i }));
    expect(screen.queryByText("older chat")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^conversations$/i }));
    expect(screen.queryByRole("button", { name: /^brand new topic$/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^back to chat$/i }));

    const box = screen.getByRole("textbox", { name: /message the agent/i });
    await user.type(box, "brand new topic{Enter}");
    await screen.findByText("you asked: brand new topic");

    await user.click(screen.getByRole("button", { name: /^conversations$/i }));
    await screen.findByRole("button", { name: /^brand new topic$/i });
  });

  // The panel is mounted once, beside the router outlet and not inside it (`Shell.tsx`),
  // so a tab switch never unmounts it — this proves the same guarantee at the level a
  // unit test can reach: the turn lives in the store, not in this component, so it keeps
  // accumulating whether or not anything is currently mounted to show it, and a fresh
  // mount against the same store picks the accumulated turn straight up.
  it("keeps a streaming turn alive in the store across an unmount, for a later remount to pick up", async () => {
    const api = createFakeApi();
    const controllable = controllableEvents();
    api.sendMessage = async (id, content) => {
      api.recordExchange(id, content, "consolidating near resistance", false);
      return controllable.events;
    };
    const store = createAgentChatStore(null, api);
    const user = userEvent.setup();
    const first = render(<AgentChat store={store} />);
    await user.click(screen.getByRole("button", { name: /open agent chat/i }));
    await screen.findByLabelText("Model");

    const box = screen.getByRole("textbox", { name: /message the agent/i });
    await user.type(box, "why is BTC flat{Enter}");
    controllable.push({ kind: "fragment", text: "consolid" });
    await screen.findByText("consolid");

    first.unmount();
    controllable.push({ kind: "fragment", text: "ating near resistance" });
    controllable.push({ kind: "complete", incomplete: false });
    await waitFor(() => expect(store.getSnapshot().turn).toBeNull());

    render(<AgentChat store={store} />);
    await screen.findByText("consolidating near resistance");
  });

  it("remembers which conversation was open across a reload", async () => {
    const api = createFakeApi();
    const older = api.seed("older chat", "luna", [
      {
        id: 1,
        role: "operator",
        content: "hello from before",
        modelId: null,
        promptVersion: null,
        incomplete: false,
        createdAt: 0,
        toolCalls: [],
      },
    ]);
    const user = userEvent.setup();
    const storage = memoryStorage();
    const { unmount } = renderChat(api, storage);
    await user.click(screen.getByRole("button", { name: /open agent chat/i }));
    await screen.findByLabelText("Model");
    await user.click(screen.getByRole("button", { name: /^conversations$/i }));
    await user.click(await screen.findByRole("button", { name: /^older chat$/i }));
    await screen.findByText("hello from before");
    unmount();

    // A fresh store and a fresh panel, as a reload would produce.
    const reloaded = createAgentChatStore(storage, api);
    expect(reloaded.getSnapshot().activeSessionId).toBe(older.id);
    render(<AgentChat store={reloaded} />);
    expect(screen.getByRole("complementary", { name: /agent chat/i })).toBeInTheDocument();
    await screen.findByText("hello from before");
  });

  it("remembers whether it was open", async () => {
    const user = userEvent.setup();
    const storage = memoryStorage();
    renderChat(createFakeApi(), storage);

    await user.click(screen.getByRole("button", { name: /open agent chat/i }));
    expect(storage.getItem(STORAGE_KEY)).toBe("expanded");

    const second = createAgentChatStore(storage, createFakeApi());
    expect(second.getSnapshot().expanded).toBe(true);
  });

  it("ignores an empty send rather than posting a blank turn", async () => {
    const user = userEvent.setup();
    renderChat();
    await user.click(screen.getByRole("button", { name: /open agent chat/i }));
    await screen.findByLabelText("Model");

    const box = screen.getByRole("textbox", { name: /message the agent/i });
    await user.type(box, "   {Enter}");

    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });

  it("renames a conversation to whatever the operator types", async () => {
    const api = createFakeApi();
    api.seed("older chat", "luna");
    const user = userEvent.setup();
    renderChat(api);
    await user.click(screen.getByRole("button", { name: /open agent chat/i }));
    await screen.findByLabelText("Model");
    await user.click(screen.getByRole("button", { name: /^conversations$/i }));

    await user.click(await screen.findByRole("button", { name: /rename older chat/i }));
    const field = screen.getByRole("textbox", { name: /rename older chat/i });
    await user.clear(field);
    await user.type(field, "EURUSD plan{Enter}");

    expect(await screen.findByRole("button", { name: /^EURUSD plan$/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^older chat$/i })).not.toBeInTheDocument();
  });

  it("abandons a rename on Escape, leaving the name the module still holds", async () => {
    const api = createFakeApi();
    api.seed("older chat", "luna");
    const user = userEvent.setup();
    renderChat(api);
    await user.click(screen.getByRole("button", { name: /open agent chat/i }));
    await screen.findByLabelText("Model");
    await user.click(screen.getByRole("button", { name: /^conversations$/i }));

    await user.click(await screen.findByRole("button", { name: /rename older chat/i }));
    const field = screen.getByRole("textbox", { name: /rename older chat/i });
    await user.clear(field);
    await user.type(field, "never mind{Escape}");

    expect(await screen.findByRole("button", { name: /^older chat$/i })).toBeInTheDocument();
  });

  it("asks before deleting, and keeps the conversation when told to", async () => {
    const api = createFakeApi();
    api.seed("older chat", "luna");
    const user = userEvent.setup();
    renderChat(api);
    await user.click(screen.getByRole("button", { name: /open agent chat/i }));
    await screen.findByLabelText("Model");
    await user.click(screen.getByRole("button", { name: /^conversations$/i }));

    await user.click(await screen.findByRole("button", { name: /delete older chat/i }));
    // The row asks rather than acting — a single mis-click on a list read far more often
    // than edited must not lose a rozmowa.
    expect(screen.getByText(/delete this conversation\?/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^keep$/i }));
    expect(await screen.findByRole("button", { name: /^older chat$/i })).toBeInTheDocument();
  });

  it("removes a confirmed conversation from the list", async () => {
    const api = createFakeApi();
    api.seed("older chat", "luna");
    api.seed("another chat", "luna");
    const user = userEvent.setup();
    renderChat(api);
    await user.click(screen.getByRole("button", { name: /open agent chat/i }));
    await screen.findByLabelText("Model");
    await user.click(screen.getByRole("button", { name: /^conversations$/i }));

    await user.click(await screen.findByRole("button", { name: /delete older chat/i }));
    await user.click(screen.getByRole("button", { name: /^delete$/i }));

    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /^older chat$/i })).not.toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: /^another chat$/i })).toBeInTheDocument();
  });
});
