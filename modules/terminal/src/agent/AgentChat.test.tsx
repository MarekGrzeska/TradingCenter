import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AgentChat } from "./AgentChat";
import {
  createAgentChatStore,
  DEFAULT_PANEL_WIDTH,
  MIN_PANEL_WIDTH,
  maxPanelWidth,
} from "./agentChatStore";
import type { AgentApi, AgentMessage, AgentModel, AgentSession, AgentToolCall } from "./agentApi";
import type { AgentStreamEvent } from "./stream";

/**
 * What only a rendered panel can hold: the rail, the catalogue on screen, a turn typed into the box, and
 * the styles that tell one tool outcome from another. What the store does is asserted against the store.
 */

function toolCall(overrides: Partial<AgentToolCall> = {}): AgentToolCall {
  return {
    roundIndex: 0,
    position: 0,
    name: "get_candles",
    arguments: { symbol: "US100", resolution: "DAY" },
    outcome: "ok",
    resultText: '{"candles": 78}',
    durationMs: 240,
    source: "server",
    ...overrides,
  };
}

const MODELS: AgentModel[] = [
  { id: "luna", displayName: "Luna", costRank: 1, inputRatePer1M: "0.2", outputRatePer1M: "1.2" },
  { id: "sol", displayName: "Sol", costRank: 3, inputRatePer1M: "5", outputRatePer1M: "30" },
];

/** Suspends between events instead of resolving them all in one microtask sweep, so a
 *  test can observe the panel mid-turn without racing the code under test. */
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
  /** What the module itself would have persisted for a turn, exposed so a test that overrides
   *  `sendMessage` for control over event timing does not also have to reinvent what a reload shows. */
  recordExchange(id: number, content: string, replyText: string, toolCalls?: AgentToolCall[]): void;
  /** Sessions the panel asked to stop, in order. */
  stopped: number[];
}

function createFakeApi(): FakeApi {
  const api: FakeApi = {
    sessions: [],
    transcripts: new Map(),
    nextId: 1,
    stopped: [],

    async stopTurn(id) {
      api.stopped.push(id);
    },

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
    async getUnclaimedToolCalls() {
      return [];
    },
    async getMessages(id) {
      return api.transcripts.get(id) ?? [];
    },
    recordExchange(id, content, replyText, toolCalls = []) {
      const transcript = api.transcripts.get(id) ?? [];
      transcript.push({
        id: transcript.length + 1,
        role: "operator",
        content,
        modelId: null,
        promptVersion: null,
        incomplete: false,
        stopped: false,
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
        incomplete: false,
        stopped: false,
        createdAt: 0,
        toolCalls,
      });
      api.transcripts.set(id, transcript);
    },

    async sendMessage(id, content) {
      const replyText = `you asked: ${content}`;
      api.recordExchange(id, content, replyText);
      return (async function* () {
        yield { kind: "fragment", text: replyText } as AgentStreamEvent;
        yield { kind: "complete", incomplete: false } as AgentStreamEvent;
      })();
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
    async chartCommand() {
      return null;
    },
    async listDrawings() {
      return [];
    },
    async patchDrawing(): Promise<never> {
      throw new Error("not used");
    },
    async deleteDrawing() {},
  };
  return api;
}

/** One drag of the handle to a screen position. Dispatched as `MouseEvent`s named for the pointer events:
 *  jsdom's own `PointerEvent` drops `clientX`, so the handler would read `undefined`. */
function drag(handle: HTMLElement, clientX: number): void {
  fireEvent(handle, new MouseEvent("pointerdown", { bubbles: true, clientX: 0 }));
  fireEvent(handle, new MouseEvent("pointermove", { bubbles: true, clientX }));
  fireEvent(handle, new MouseEvent("pointerup", { bubbles: true, clientX }));
}

function renderChat(api: FakeApi = createFakeApi()) {
  const store = createAgentChatStore(null, api);
  return { api, store, ...render(<AgentChat store={store} />) };
}

async function openPanel(api: FakeApi = createFakeApi()) {
  const user = userEvent.setup();
  const rendered = renderChat(api);
  await user.click(screen.getByRole("button", { name: /open agent chat/i }));
  return { user, ...rendered };
}

describe("AgentChat", () => {
  it("expands from the rail with the module's own catalogue, and collapses back to it", async () => {
    const { user } = await openPanel();

    expect(screen.getByRole("complementary", { name: /agent chat/i })).toBeInTheDocument();
    const select = await screen.findByLabelText("Model");
    // The rates the module published, rendered as they arrived: per million, which is
    // what `agent/contract.py` sends, and never rescaled here.
    expect(screen.getByRole("option", { name: /luna.*0\.2.*1\.2.*per 1M/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /sol.*5.*30.*per 1M/i })).toBeInTheDocument();
    await user.selectOptions(select, "sol");
    expect(select).toHaveValue("sol");

    await user.click(screen.getByRole("button", { name: /collapse agent chat/i }));
    expect(screen.getByRole("button", { name: /open agent chat/i })).toBeInTheDocument();
    expect(screen.queryByRole("complementary", { name: /agent chat/i })).not.toBeInTheDocument();
  });

  it("shows waiting before the first fragment, streams the reply in, then settles it", async () => {
    const api = createFakeApi();
    const controllable = controllableEvents();
    api.sendMessage = async (id, content) => {
      // Same write the module ends up doing — only the pacing of the events is under
      // this test's control, not what a reload afterwards would show.
      api.recordExchange(id, content, "consolidating");
      return controllable.events;
    };
    const { user } = await openPanel(api);
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
    await screen.findByText("consolidating");
  });

  it("offers Stop while the turn runs, and asks the module to end it", async () => {
    // `terminal-agent-chat` spec, "Operator zatrzymuje trwającą odpowiedź"
    const api = createFakeApi();
    const controllable = controllableEvents();
    api.sendMessage = async (id, content) => {
      api.recordExchange(id, content, "half an ", []);
      return controllable.events;
    };
    const { user } = await openPanel(api);
    await screen.findByLabelText("Model");

    // Nothing to stop before there is a turn.
    expect(screen.queryByRole("button", { name: "Stop" })).not.toBeInTheDocument();

    await user.type(screen.getByRole("textbox", { name: /message the agent/i }), "long question");
    await user.click(screen.getByRole("button", { name: "Send" }));

    const stop = await screen.findByRole("button", { name: "Stop" });
    expect(screen.queryByRole("button", { name: "Send" })).not.toBeInTheDocument();

    controllable.push({ kind: "fragment", text: "half an " });
    await screen.findByText("half an");
    await user.click(stop);
    await waitFor(() => expect(api.stopped).toHaveLength(1));

    controllable.push({ kind: "stopped" });
    // The turn is over: the composer takes questions again.
    await screen.findByRole("button", { name: "Send" });
  });

  it("shows a stopped reply as stopped, not as a break", async () => {
    // `terminal-agent-chat` spec, "Odpowiedź zatrzymana nie jest błędem"
    const api = createFakeApi();
    const session = api.seed("earlier", "luna", [
      {
        id: 1,
        role: "operator",
        content: "long question",
        modelId: null,
        promptVersion: null,
        incomplete: false,
        stopped: false,
        createdAt: 0,
        toolCalls: [],
      },
      {
        id: 2,
        role: "agent",
        content: "half an answer",
        modelId: "luna",
        promptVersion: "v1",
        incomplete: true,
        stopped: true,
        createdAt: 0,
        toolCalls: [],
      },
    ]);
    void session;
    const { user } = await openPanel(api);
    await screen.findByLabelText("Model");

    await user.click(screen.getByRole("button", { name: /^conversations$/i }));
    await user.click(await screen.findByRole("button", { name: /^earlier$/i }));

    await screen.findByText("half an answer");
    expect(screen.getByText(/stopped by you/i)).toBeInTheDocument();
    expect(screen.queryByText(/broke off/i)).not.toBeInTheDocument();
  });

  it("says the model picker is unavailable when the catalogue cannot be read, and offers no select", async () => {
    const api = createFakeApi();
    api.listModels = async () => {
      throw new Error("models unreachable");
    };
    await openPanel(api);

    await screen.findByText(/model picker unavailable/i);
    expect(screen.queryByLabelText("Model")).not.toBeInTheDocument();
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
        stopped: false,
        createdAt: 0,
        toolCalls: [],
      },
    ]);
    const { user } = await openPanel(api);
    await screen.findByLabelText("Model");

    await user.click(screen.getByRole("button", { name: /^conversations$/i }));
    await user.click(await screen.findByRole("button", { name: /^older chat$/i }));

    await screen.findByText("hello from before");
    expect(screen.getByRole("textbox", { name: /message the agent/i })).toBeInTheDocument();
  });

  it("tells a refusal, an unreachable server and a successful call apart, behind one click", async () => {
    const api = createFakeApi();
    const session = api.seed("older chat", "luna");
    api.recordExchange(session.id, "summarise US100", "I could not check all of it", [
      toolCall(),
      toolCall({ position: 1, name: "summarize_range", outcome: "refused", durationMs: 18 }),
      toolCall({ position: 2, name: "describe_coverage", outcome: "unavailable", durationMs: 3 }),
    ]);
    const { user } = await openPanel(api);
    await screen.findByLabelText("Model");
    await user.click(screen.getByRole("button", { name: /^conversations$/i }));
    await user.click(await screen.findByRole("button", { name: /^older chat$/i }));

    await screen.findByText("get_candles");
    expect(screen.getByText("ok")).toHaveClass("text-ink-muted");
    // A refusal is the archive answering "not like that"; an unreachable server means nothing was asked.
    // Reading the second as the first is how "the archive has no data" gets said about data it has.
    expect(screen.getByText("refused")).toHaveClass("text-warning");
    expect(screen.getByText("no answer")).toHaveClass("text-critical");
    expect(screen.queryByText(/incomplete/i)).not.toBeInTheDocument();

    // Collapsed by default: a turn is allowed eight calls, and eight open results would
    // bury the conversation they were made for.
    expect(screen.queryByText(/"symbol":"US100"/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /expand get_candles/i }));
    expect(screen.getByText(/"symbol":"US100"/)).toBeInTheDocument();
    expect(screen.getByText('{"candles": 78}')).toBeInTheDocument();
  });

  it("gives the panel the width the operator drags it to, and stops at the bounds", async () => {
    // `terminal-agent-chat` spec, "Operator poszerza panel" and "Ciągnięcie poza granicę"
    await openPanel();
    const panel = screen.getByRole("complementary", { name: /agent chat/i });
    const handle = screen.getByRole("separator", { name: /resize agent chat/i });
    expect(panel).toHaveStyle({ width: `${DEFAULT_PANEL_WIDTH}px` });

    // jsdom has no layout, so the drag is the three pointer events themselves — which is
    // also all the component reads.
    drag(handle, window.innerWidth - 600);
    expect(panel).toHaveStyle({ width: "600px" });

    // Past the far end: the panel stops, and the tab beside it keeps its share.
    drag(handle, 0);
    expect(panel).toHaveStyle({ width: `${maxPanelWidth(window.innerWidth)}px` });

    // And past the near end.
    drag(handle, window.innerWidth);
    expect(panel).toHaveStyle({ width: `${MIN_PANEL_WIDTH}px` });
  });

  it("resizes from the keyboard, in steps and to either bound", async () => {
    // `terminal-agent-chat` spec, "Chwyt z klawiatury"
    const { user } = await openPanel();
    const panel = screen.getByRole("complementary", { name: /agent chat/i });
    const handle = screen.getByRole("separator", { name: /resize agent chat/i });

    handle.focus();
    await user.keyboard("{ArrowLeft}");
    expect(panel).toHaveStyle({ width: `${DEFAULT_PANEL_WIDTH + 16}px` });
    await user.keyboard("{ArrowRight}{ArrowRight}");
    expect(panel).toHaveStyle({ width: `${DEFAULT_PANEL_WIDTH - 16}px` });

    await user.keyboard("{Home}");
    expect(panel).toHaveStyle({ width: `${MIN_PANEL_WIDTH}px` });
    await user.keyboard("{End}");
    expect(panel).toHaveStyle({ width: `${maxPanelWidth(window.innerWidth)}px` });
  });

  it("keeps the operator's width through collapsing and expanding again", async () => {
    const { user } = await openPanel();
    const handle = screen.getByRole("separator", { name: /resize agent chat/i });
    drag(handle, window.innerWidth - 520);

    await user.click(screen.getByRole("button", { name: /collapse agent chat/i }));
    await user.click(screen.getByRole("button", { name: /open agent chat/i }));

    expect(screen.getByRole("complementary", { name: /agent chat/i })).toHaveStyle({
      width: "520px",
    });
  });

  it("opens no wider than the window allows, whatever was saved", async () => {
    // `terminal-agent-chat` spec, "Okno węższe niż zapamiętana szerokość"
    const storage = window.localStorage;
    storage.setItem("terminal.agentChat.width.v1", "3000");
    try {
      const api = createFakeApi();
      const store = createAgentChatStore(storage, api);
      render(<AgentChat store={store} />);
      await userEvent.setup().click(screen.getByRole("button", { name: /open agent chat/i }));

      expect(screen.getByRole("complementary", { name: /agent chat/i })).toHaveStyle({
        width: `${maxPanelWidth(window.innerWidth)}px`,
      });
    } finally {
      storage.removeItem("terminal.agentChat.width.v1");
    }
  });
});
