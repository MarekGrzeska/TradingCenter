import { describe, expect, it } from "vitest";
import { waitFor } from "@testing-library/react";
import {
  createAgentChatStore,
  DEFAULT_PANEL_WIDTH,
  MIN_PANEL_WIDTH,
  maxPanelWidth,
  STORAGE_KEY,
} from "./agentChatStore";
import type {
  AgentApi,
  AgentMessage,
  AgentModel,
  AgentSession,
  AgentToolCall,
} from "./agentApi";
import type { AgentStreamEvent } from "./stream";
import { toastStore } from "../ui/toastStore";

const MODELS: AgentModel[] = [
  { id: "luna", displayName: "Luna", costRank: 1, inputRatePer1M: "0.2", outputRatePer1M: "1.2" },
  { id: "sol", displayName: "Sol", costRank: 3, inputRatePer1M: "5", outputRatePer1M: "30" },
];

async function* fromArray(events: AgentStreamEvent[]): AsyncGenerator<AgentStreamEvent> {
  yield* events;
}

const CANDLES_CALL: AgentToolCall = {
  roundIndex: 0,
  position: 0,
  name: "get_candles",
  arguments: { symbol: "US100", resolution: "DAY" },
  outcome: "ok",
  resultText: '{"candles": 78}',
  durationMs: 240,
  source: "server",
};

const REFUSED_CALL: AgentToolCall = {
  roundIndex: 0,
  position: 1,
  name: "summarize_range",
  arguments: { symbol: "US100" },
  outcome: "refused",
  resultText: "market-data refused: no such pair",
  durationMs: 18,
  source: "server",
};

/** A stream that only advances when the test tells it to — the fixed-array fake below
 *  resolves purely through microtasks, which can finish a whole turn before a
 *  timer-based `waitFor` gets to look; this one genuinely suspends between events, so a
 *  test asserting something about the "streaming" window is not racing the code under
 *  test. */
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
  failListModels: boolean;
  failListSessions: boolean;
  failGetMessages: boolean;
  failCreateSession: boolean;
  failSendMessage: boolean;
  failRenameSession: boolean;
  failDeleteSession: boolean;
  /** Sessions `stopTurn` was called for, in order — what the panel asked the module to
   *  end, as opposed to what the module then did about it. */
  stopped: number[];
  failStopTurn: boolean;
  /** What `sendMessage` hands back, set per test — a plain event list by default. */
  script: AgentStreamEvent[];
  /** Seeds a titled, already-exchanged conversation, the way one would exist in the
   *  module before the panel ever opened — through `nextId`, so it can never collide
   *  with a session `send()` goes on to create in the same test. */
  seed(title: string, modelId: string): AgentSession;
}

function createFakeApi(): FakeApi {
  const api: FakeApi = {
    sessions: [],
    transcripts: new Map(),
    nextId: 1,
    stopped: [],
    failStopTurn: false,
    failListModels: false,
    failListSessions: false,
    failGetMessages: false,
    failCreateSession: false,
    failSendMessage: false,
    failRenameSession: false,
    failDeleteSession: false,
    script: [{ kind: "complete", incomplete: false }],

    seed(title, modelId) {
      const session: AgentSession = {
        id: api.nextId++,
        title,
        currentModelId: modelId,
        createdAt: 0,
        lastActiveAt: 0,
      };
      api.sessions.push(session);
      api.transcripts.set(session.id, []);
      return session;
    },

    async listModels() {
      if (api.failListModels) throw new Error("models unreachable");
      return MODELS;
    },
    async listSessions() {
      if (api.failListSessions) throw new Error("sessions unreachable");
      // Same filter the module applies: only conversations that have a title.
      return api.sessions.filter((s) => s.title !== null);
    },
    async getSession(id) {
      const found = api.sessions.find((s) => s.id === id);
      if (!found) throw new Error("no such session");
      return found;
    },
    async createSession(modelId) {
      if (api.failCreateSession) throw new Error("agent is not reachable");
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
      if (api.failRenameSession) throw new Error("agent is not reachable");
      const found = api.sessions.find((s) => s.id === id);
      if (!found) throw new Error("no such session");
      found.title = title;
      return found;
    },
    async deleteSession(id) {
      if (api.failDeleteSession) throw new Error("agent is not reachable");
      const index = api.sessions.findIndex((s) => s.id === id);
      if (index === -1) throw new Error("no such session");
      // The module soft-deletes and the transcript stays in its database; from this side
      // the row and its messages are simply gone, which is all the terminal can observe.
      api.sessions.splice(index, 1);
      api.transcripts.delete(id);
    },
    async stopTurn(id) {
      if (api.failStopTurn) throw new Error("agent is not reachable");
      api.stopped.push(id);
    },
    async getUnclaimedToolCalls() {
      return [];
    },
    async getMessages(id) {
      if (api.failGetMessages) throw new Error("agent is not reachable");
      return api.transcripts.get(id) ?? [];
    },
    async sendMessage(id, content) {
      if (api.failSendMessage) throw new Error("agent is not reachable");
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
      // The module's own behaviour: a title appears once there has been an exchange.
      if (session && session.title === null) session.title = content.slice(0, 40);

      const text = api.script
        .filter((e): e is Extract<AgentStreamEvent, { kind: "fragment" }> => e.kind === "fragment")
        .map((e) => e.text)
        .join("");
      // Also the module's own behaviour: whatever the stream announced ends up on the
      // reply in the transcript, in the same shape (`agent/contract.py`, `ToolCallOut`).
      const calls = api.script
        .filter((e): e is Extract<AgentStreamEvent, { kind: "toolCall" }> => e.kind === "toolCall")
        .map((e) => e.call);
      const broke = api.script.some((e) => e.kind === "error");
      if (text || !broke) {
        transcript.push({
          id: transcript.length + 1,
          role: "agent",
          content: text,
          modelId: session?.currentModelId ?? null,
          promptVersion: "v1",
          incomplete: broke,
          stopped: false,
          createdAt: 0,
          toolCalls: calls,
        });
      }
      api.transcripts.set(id, transcript);
      return fromArray(api.script);
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

function memoryStorage(seed: Record<string, string> = {}): Storage {
  const entries = new Map(Object.entries(seed));
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

describe("createAgentChatStore", () => {
  it("loads the model catalogue and the session list once the panel expands", async () => {
    const api = createFakeApi();
    const older = api.seed("why is BTC flat", "luna");
    const store = createAgentChatStore(null, api);

    expect(store.getSnapshot().modelsStatus).toBe("loading");
    store.setExpanded(true);

    await waitFor(() => expect(store.getSnapshot().modelsStatus).toBe("ready"));
    expect(store.getSnapshot().models).toEqual(MODELS);
    expect(store.getSnapshot().selectedModelId).toBe("luna");
    await waitFor(() => expect(store.getSnapshot().sessionsStatus).toBe("ready"));
    expect(store.getSnapshot().sessions.map((s) => s.id)).toEqual([older.id]);
  });

  it("says the catalogue could not load rather than falling back to a built-in list", async () => {
    const api = createFakeApi();
    api.failListModels = true;
    const store = createAgentChatStore(null, api);

    store.setExpanded(true);
    await waitFor(() => expect(store.getSnapshot().modelsStatus).toBe("unreachable"));
    expect(store.getSnapshot().models).toEqual([]);
  });

  it("streams fragments into the turn, then reloads the canonical transcript on completion", async () => {
    const api = createFakeApi();
    api.script = [
      { kind: "fragment", text: "why is " },
      { kind: "fragment", text: "BTC flat" },
      { kind: "complete", incomplete: false },
    ];
    const store = createAgentChatStore(null, api);
    store.setExpanded(true);
    await waitFor(() => expect(store.getSnapshot().modelsStatus).toBe("ready"));

    const seenTurns: unknown[] = [];
    store.subscribe(() => seenTurns.push(store.getSnapshot().turn));

    store.send("why is BTC flat");

    await waitFor(() => expect(store.getSnapshot().turn).toBeNull());

    expect(seenTurns).toContainEqual({ status: "waiting", toolCalls: [] });
    expect(seenTurns).toContainEqual({ status: "streaming", text: "why is ", toolCalls: [] });
    expect(seenTurns).toContainEqual({
      status: "streaming",
      text: "why is BTC flat",
      toolCalls: [],
    });

    const { messages, activeSessionId } = store.getSnapshot();
    expect(activeSessionId).not.toBeNull();
    expect(messages.map((m) => ({ role: m.role, text: m.text, incomplete: m.incomplete }))).toEqual([
      { role: "operator", text: "why is BTC flat", incomplete: false },
      { role: "agent", text: "why is BTC flat", incomplete: false },
    ]);
    // Every id is the module's own — nothing local survives a completed turn.
    expect(messages.every((m) => typeof m.id === "number")).toBe(true);
  });

  it("does not create a session a second time for the same conversation", async () => {
    const api = createFakeApi();
    const store = createAgentChatStore(null, api);
    store.setExpanded(true);
    await waitFor(() => expect(store.getSnapshot().modelsStatus).toBe("ready"));

    store.send("first");
    await waitFor(() => expect(store.getSnapshot().turn).toBeNull());
    const firstSessionId = store.getSnapshot().activeSessionId;

    store.send("second");
    await waitFor(() => expect(store.getSnapshot().turn).toBeNull());

    expect(store.getSnapshot().activeSessionId).toBe(firstSessionId);
    expect(api.sessions).toHaveLength(1);
  });

  it("marks a mid-stream break as incomplete and keeps what arrived, instead of losing it", async () => {
    const api = createFakeApi();
    api.script = [
      { kind: "fragment", text: "consolidating" },
      { kind: "error", message: "the model call failed" },
    ];
    const store = createAgentChatStore(null, api);
    store.setExpanded(true);
    await waitFor(() => expect(store.getSnapshot().modelsStatus).toBe("ready"));

    store.send("why is BTC flat");
    await waitFor(() => expect(store.getSnapshot().turn).toBeNull());

    const { messages } = store.getSnapshot();
    const reply = messages.find((m) => m.role === "agent");
    expect(reply).toMatchObject({ text: "consolidating", incomplete: true });
  });

  it("falls back to a local, marked-incomplete bubble when the reload after a break also fails", async () => {
    const api = createFakeApi();
    api.script = [
      { kind: "fragment", text: "consolidating" },
      { kind: "error", message: "the model call failed" },
    ];
    const store = createAgentChatStore(null, api);
    store.setExpanded(true);
    await waitFor(() => expect(store.getSnapshot().modelsStatus).toBe("ready"));

    store.send("why is BTC flat");
    // The reload `finishTurn` issues right after the break is what must fail here —
    // flipped on right after the send so the initial "does the module exist" catalogue
    // load above is unaffected.
    api.failGetMessages = true;
    await waitFor(() => expect(store.getSnapshot().turn).toBeNull());

    const { messages } = store.getSnapshot();
    expect(messages.map((m) => ({ role: m.role, text: m.text, incomplete: m.incomplete }))).toEqual([
      { role: "operator", text: "why is BTC flat", incomplete: false },
      { role: "agent", text: "consolidating", incomplete: true },
    ]);
  });

  it("says the module is unreachable and shows no agent reply when nothing was ever accepted", async () => {
    const api = createFakeApi();
    api.failCreateSession = true;
    const store = createAgentChatStore(null, api);
    store.setExpanded(true);
    await waitFor(() => expect(store.getSnapshot().modelsStatus).toBe("ready"));

    store.send("why is BTC flat");
    await waitFor(() => {
      expect(store.getSnapshot().turn).toMatchObject({ status: "unreachable" });
    });

    const { messages } = store.getSnapshot();
    // The operator's own typed text stays — only a reply that never happened is barred.
    expect(messages).toHaveLength(1);
    expect(messages[0]).toMatchObject({ role: "operator", text: "why is BTC flat" });
    expect(messages.some((m) => m.role === "agent")).toBe(false);
  });

  it("loads a picked conversation's transcript from the module, not from memory", async () => {
    const api = createFakeApi();
    const older = api.seed("older chat", "luna");
    api.transcripts.set(older.id, [
      {
        id: 1,
        role: "operator",
        content: "hello",
        modelId: null,
        promptVersion: null,
        incomplete: false,
        stopped: false,
        createdAt: 0,
        toolCalls: [],
      },
    ]);
    const store = createAgentChatStore(null, api);
    store.setExpanded(true);
    await waitFor(() => expect(store.getSnapshot().sessionsStatus).toBe("ready"));

    store.openSession(older.id);
    await waitFor(() => expect(store.getSnapshot().transcriptStatus).toBe("ready"));

    expect(store.getSnapshot().messages).toEqual([
      { id: 1, role: "operator", text: "hello", incomplete: false, stopped: false, toolCalls: [] },
    ]);
    expect(store.getSnapshot().selectedModelId).toBe("luna");
  });

  it("starts a new conversation empty, off the list until the first exchange", async () => {
    const api = createFakeApi();
    const older = api.seed("older chat", "luna");
    const store = createAgentChatStore(null, api);
    store.setExpanded(true);
    await waitFor(() => expect(store.getSnapshot().sessionsStatus).toBe("ready"));

    store.openSession(older.id);
    await waitFor(() => expect(store.getSnapshot().transcriptStatus).toBe("ready"));

    store.newSession();
    expect(store.getSnapshot().activeSessionId).toBeNull();
    expect(store.getSnapshot().messages).toEqual([]);

    store.send("brand new conversation");
    await waitFor(() => expect(store.getSnapshot().turn).toBeNull());
    await waitFor(() => expect(store.getSnapshot().sessions).toHaveLength(2));
  });

  it("ignores openSession and newSession while a turn is in flight", async () => {
    const api = createFakeApi();
    const older = api.seed("older chat", "luna");
    const store = createAgentChatStore(null, api);
    store.setExpanded(true);
    await waitFor(() => expect(store.getSnapshot().sessionsStatus).toBe("ready"));

    const controllable = controllableEvents();
    api.sendMessage = async () => controllable.events;

    store.send("why is BTC flat");
    controllable.push({ kind: "fragment", text: "still going" });
    await waitFor(() =>
      expect(store.getSnapshot().turn).toEqual({
        status: "streaming",
        text: "still going",
        toolCalls: [],
      }),
    );

    const activeBefore = store.getSnapshot().activeSessionId;
    store.openSession(older.id);
    store.newSession();
    expect(store.getSnapshot().activeSessionId).toBe(activeBefore);
    // Neither call so much as started a transcript load for the other conversation.
    expect(store.getSnapshot().transcriptStatus).toBe("ready");

    controllable.push({ kind: "complete", incomplete: false });
    await waitFor(() => expect(store.getSnapshot().turn).toBeNull());
  });

  it("PATCHes the model for the active conversation and reverts it if the module refuses", async () => {
    const api = createFakeApi();
    const older = api.seed("older chat", "luna");
    const store = createAgentChatStore(null, api);
    store.setExpanded(true);
    await waitFor(() => expect(store.getSnapshot().sessionsStatus).toBe("ready"));
    store.openSession(older.id);
    await waitFor(() => expect(store.getSnapshot().transcriptStatus).toBe("ready"));

    store.setModel("sol");
    await waitFor(() => expect(store.getSnapshot().selectedModelId).toBe("sol"));
    expect(api.sessions[0].currentModelId).toBe("sol");

    const failing = createAgentChatStore(null, api);
    api.setSessionModel = async () => {
      throw new Error("no such model: made-up");
    };
    failing.setExpanded(true);
    await waitFor(() => expect(failing.getSnapshot().sessionsStatus).toBe("ready"));
    failing.openSession(older.id);
    await waitFor(() => expect(failing.getSnapshot().selectedModelId).toBe("sol"));
    failing.setModel("made-up");
    await waitFor(() => expect(failing.getSnapshot().selectedModelId).toBe("sol"));
  });

  it("ignores a blank send rather than posting an empty turn", async () => {
    const api = createFakeApi();
    const store = createAgentChatStore(null, api);
    store.setExpanded(true);
    await waitFor(() => expect(store.getSnapshot().modelsStatus).toBe("ready"));

    store.send("   ");
    expect(store.getSnapshot().turn).toBeNull();
    expect(store.getSnapshot().messages).toEqual([]);
  });

  it("remembers the collapse state under the same key the mockup used", () => {
    const storage = memoryStorage();
    const store = createAgentChatStore(storage, createFakeApi());
    store.setExpanded(true);
    expect(storage.getItem(STORAGE_KEY)).toBe("expanded");
    store.setExpanded(false);
    expect(storage.getItem(STORAGE_KEY)).toBe("collapsed");
  });

  it("remembers and restores the last open conversation across a reload", async () => {
    const api = createFakeApi();
    const older = api.seed("older chat", "luna");
    api.transcripts.set(older.id, [
      {
        id: 1,
        role: "operator",
        content: "hello",
        modelId: null,
        promptVersion: null,
        incomplete: false,
        stopped: false,
        createdAt: 0,
        toolCalls: [],
      },
    ]);
    const storage = memoryStorage();
    const first = createAgentChatStore(storage, api);
    first.setExpanded(true);
    await waitFor(() => expect(first.getSnapshot().sessionsStatus).toBe("ready"));
    first.openSession(older.id);
    await waitFor(() => expect(first.getSnapshot().transcriptStatus).toBe("ready"));

    // A fresh store, as a reload would construct — reads back the same conversation and
    // loads it without anybody clicking it again. The load is asked for by the panel's
    // mount, not by construction: construction happens during `import`, before sign-in
    // has been resolved, and a request made there never carries a token.
    const second = createAgentChatStore(storage, api);
    expect(second.getSnapshot().activeSessionId).toBe(older.id);
    second.ensureLoaded();
    await waitFor(() => expect(second.getSnapshot().transcriptStatus).toBe("ready"));
    expect(second.getSnapshot().messages).toEqual([
      { id: 1, role: "operator", text: "hello", incomplete: false, stopped: false, toolCalls: [] },
    ]);
  });

  it("renames a conversation only once the module has agreed", async () => {
    const api = createFakeApi();
    const older = api.seed("older chat", "luna");
    const store = createAgentChatStore(null, api);
    store.setExpanded(true);
    await waitFor(() => expect(store.getSnapshot().sessionsStatus).toBe("ready"));

    store.renameSession(older.id, "  EURUSD plan  ");
    await waitFor(() =>
      expect(store.getSnapshot().sessions[0].title).toBe("EURUSD plan"),
    );
  });

  it("keeps the old name when the rename is refused, rather than showing one nothing holds", async () => {
    const api = createFakeApi();
    const older = api.seed("older chat", "luna");
    api.failRenameSession = true;
    const store = createAgentChatStore(null, api);
    store.setExpanded(true);
    await waitFor(() => expect(store.getSnapshot().sessionsStatus).toBe("ready"));

    store.renameSession(older.id, "EURUSD plan");
    await waitFor(() => expect(api.failRenameSession).toBe(true));
    expect(store.getSnapshot().sessions[0].title).toBe("older chat");
  });

  it("clears the panel when the conversation it is showing is deleted", async () => {
    const api = createFakeApi();
    const older = api.seed("older chat", "luna");
    const store = createAgentChatStore(null, api);
    store.setExpanded(true);
    await waitFor(() => expect(store.getSnapshot().sessionsStatus).toBe("ready"));

    store.openSession(older.id);
    await waitFor(() => expect(store.getSnapshot().activeSessionId).toBe(older.id));

    store.deleteSession(older.id);
    // Not left on screen: the module answers 404 for it now, so a transcript still
    // showing would be one nothing can be added to.
    await waitFor(() => expect(store.getSnapshot().activeSessionId).toBeNull());
    expect(store.getSnapshot().messages).toEqual([]);
    expect(store.getSnapshot().sessions).toEqual([]);
  });

  it("asks for nothing at construction, and everything once the panel mounts", async () => {
    /**
     * The production bug of 13 August 2026. The store is a module-level const, so
     * constructing it ran during `import` — before `main.tsx` had awaited
     * `identity.initialize()`. Every request it made there asked an MSAL that had not
     * resolved the session yet, was refused, and never reached the network. The session
     * list recovered by itself, because `finishTurn` reloads it after every turn; the
     * model catalogue had no second chance and the picker read "unavailable" for the life
     * of the page, while the module's own log showed no request for it at all.
     */
    const api = createFakeApi();
    api.seed("older chat", "luna");
    let calls = 0;
    const counted = { ...api, listModels: async () => (calls++, MODELS) };
    const storage = memoryStorage({ [STORAGE_KEY]: "expanded" });

    const store = createAgentChatStore(storage, counted);
    expect(store.getSnapshot().expanded).toBe(true);
    expect(calls).toBe(0);

    store.ensureLoaded();

    await waitFor(() => expect(store.getSnapshot().modelsStatus).toBe("ready"));
    expect(calls).toBe(1);
  });

  it("retries a catalogue that failed, rather than staying unavailable for the page", async () => {
    const api = createFakeApi();
    api.failListModels = true;
    const store = createAgentChatStore(null, api);
    store.setExpanded(true);
    await waitFor(() => expect(store.getSnapshot().modelsStatus).toBe("unreachable"));

    // The old gate was "has the panel ever been opened", so this second ask did nothing
    // and the picker stayed broken until the operator reloaded — which reproduced the
    // failure rather than clearing it.
    api.failListModels = false;
    store.ensureLoaded();

    await waitFor(() => expect(store.getSnapshot().modelsStatus).toBe("ready"));
    expect(store.getSnapshot().models).toHaveLength(MODELS.length);
  });

  it("shows a tool call while the turn is still waiting for the first fragment", async () => {
    const api = createFakeApi();
    const store = createAgentChatStore(null, api);
    store.setExpanded(true);
    await waitFor(() => expect(store.getSnapshot().modelsStatus).toBe("ready"));
    const controllable = controllableEvents();
    api.sendMessage = async () => controllable.events;

    store.send("summarise US100");
    controllable.push({ kind: "toolCall", call: CANDLES_CALL });

    // Still "waiting": no text has arrived, and claiming "streaming" would swap the
    // panel's "thinking…" for an empty bubble.
    await waitFor(() =>
      expect(store.getSnapshot().turn).toEqual({ status: "waiting", toolCalls: [CANDLES_CALL] }),
    );

    controllable.push({ kind: "fragment", text: "it rose 0.6%" });
    await waitFor(() =>
      expect(store.getSnapshot().turn).toEqual({
        status: "streaming",
        text: "it rose 0.6%",
        toolCalls: [CANDLES_CALL],
      }),
    );
  });

  it("keeps the turn's calls on the reply the transcript hands back", async () => {
    const api = createFakeApi();
    api.script = [
      { kind: "toolCall", call: CANDLES_CALL },
      { kind: "toolCall", call: REFUSED_CALL },
      { kind: "fragment", text: "it rose 0.6%" },
      { kind: "complete", incomplete: false },
    ];
    const store = createAgentChatStore(null, api);
    store.setExpanded(true);
    await waitFor(() => expect(store.getSnapshot().modelsStatus).toBe("ready"));

    store.send("summarise US100");
    await waitFor(() => expect(store.getSnapshot().turn).toBeNull());

    const { messages } = store.getSnapshot();
    expect(messages.at(-1)?.toolCalls).toEqual([CANDLES_CALL, REFUSED_CALL]);
    // A refusal is a result, not a broken reply.
    expect(messages.at(-1)?.incomplete).toBe(false);
    expect(messages[0].toolCalls).toEqual([]);
  });

  it("keeps the calls on screen when the stream breaks and the module cannot be reloaded", async () => {
    const api = createFakeApi();
    api.script = [
      { kind: "toolCall", call: CANDLES_CALL },
      { kind: "fragment", text: "cut o" },
      { kind: "error", message: "the model call failed" },
    ];
    const store = createAgentChatStore(null, api);
    store.setExpanded(true);
    await waitFor(() => expect(store.getSnapshot().modelsStatus).toBe("ready"));

    store.send("summarise US100");
    await waitFor(() => expect(store.getSnapshot().messages).toHaveLength(1));
    api.failGetMessages = true;

    await waitFor(() => expect(store.getSnapshot().turn).toBeNull());

    const reply = store.getSnapshot().messages.at(-1);
    // The locally reconstructed bubble — the one thing that explains a reply that broke
    // off is what the agent had read by then.
    expect(reply).toMatchObject({ text: "cut o", incomplete: true });
    expect(reply?.toolCalls).toEqual([CANDLES_CALL]);
  });

  it("leaves the open conversation alone when a different one is deleted", async () => {
    const api = createFakeApi();
    const keep = api.seed("keep me", "luna");
    const drop = api.seed("drop me", "luna");
    const store = createAgentChatStore(null, api);
    store.setExpanded(true);
    await waitFor(() => expect(store.getSnapshot().sessionsStatus).toBe("ready"));

    store.openSession(keep.id);
    await waitFor(() => expect(store.getSnapshot().activeSessionId).toBe(keep.id));

    store.deleteSession(drop.id);
    await waitFor(() => expect(store.getSnapshot().sessions).toHaveLength(1));
    expect(store.getSnapshot().activeSessionId).toBe(keep.id);
    expect(store.getSnapshot().sessions[0].id).toBe(keep.id);
  });
});


describe("createAgentChatStore — the chart the agent can set", () => {
  it("sends what the terminal is drawing with the turn", async () => {
    const api = createFakeApi();
    const sent: Array<unknown> = [];
    const wrapped = {
      ...api,
      sendMessage: (id: number, content: string, signal: AbortSignal, chart?: unknown) => {
        sent.push(chart);
        return api.sendMessage(id, content, signal);
      },
    };
    const snapshot = {
      symbol: "US100",
      resolution: "HOUR" as const,
      indicators: [{ id: "ema", params: { period: 200 }, color: null }],
    };
    const store = createAgentChatStore(null, wrapped as typeof api, async () => null, () => snapshot);

    store.send("what do you see?");
    await waitFor(() => expect(store.getSnapshot().turn).toBeNull());

    expect(sent).toEqual([snapshot]);
  });

  it("says what the agent did to the chart, once the turn is over", async () => {
    const api = createFakeApi();
    const store = createAgentChatStore(null, api, async () => ({
      applied: ["EMA period 200"],
      skipped: [],
    }));

    expect(store.getSnapshot().chartNotice).toBeNull();
    store.send("show me the slow average");

    await waitFor(() =>
      expect(store.getSnapshot().chartNotice).toBe("The agent set the chart: EMA period 200."),
    );
  });

  it("keeps the conversation when the chart read fails", async () => {
    const api = createFakeApi();
    const store = createAgentChatStore(null, api, async () => null);

    store.send("hello");
    await waitFor(() => expect(store.getSnapshot().turn).toBeNull());

    expect(store.getSnapshot().chartNotice).toBeNull();
    expect(store.getSnapshot().messages.map((m) => m.role)).toEqual(["operator", "agent"]);
  });

  /** A drawings store that answers one fixed difference and records that it was asked. */
  function fakeDrawings(change = { added: 0, removed: 0 }) {
    const store = {
      calls: 0,
      subscribe: () => () => {},
      getSnapshot: () => ({}),
      ensureLoaded: () => {},
      refresh: async () => change,
      async refreshAll() {
        store.calls += 1;
        return change;
      },
      remove: async () => null,
      patch: async () => null,
    };
    return store;
  }

  it("says what the agent drew, once the turn is over", async () => {
    const api = createFakeApi();
    const drawings = fakeDrawings({ added: 1, removed: 0 });
    const store = createAgentChatStore(null, api, async () => null, () => null, drawings);

    store.send("mark the weekly high");

    await waitFor(() =>
      expect(store.getSnapshot().chartNotice).toBe("The agent drew 1 object on the chart."),
    );
  });

  it("says both in one sentence when the agent set the chart and drew on it", async () => {
    // One channel, not two — `terminal-agent-chat` spec, "tą samą drogą i w tej samej
    // chwili co o poleceniu wykresu".
    const api = createFakeApi();
    const store = createAgentChatStore(
      null,
      api,
      async () => ({ applied: ["EMA period 200"], skipped: [] }),
      () => null,
      fakeDrawings({ added: 2, removed: 1 }),
    );

    store.send("show the slow average and mark the range");

    await waitFor(() =>
      expect(store.getSnapshot().chartNotice).toBe(
        "The agent set the chart: EMA period 200. The agent drew 2 objects and removed 1 on the chart.",
      ),
    );
  });

  it("reads the objects after every turn, even one that set no chart", async () => {
    const api = createFakeApi();
    const drawings = fakeDrawings();
    const store = createAgentChatStore(null, api, async () => null, () => null, drawings);

    store.send("hello");
    await waitFor(() => expect(store.getSnapshot().turn).toBeNull());

    // The read happens because the turn ended, not because the chart command read found
    // something: the agent may have drawn without touching the chart at all.
    await waitFor(() => expect(drawings.calls).toBeGreaterThanOrEqual(1));
    expect(store.getSnapshot().chartNotice).toBeNull();
  });

  it("says a turn ended, for whatever is showing state this store cannot read", async () => {
    // Since `teams-mcp` a chat writes into another module — a team created, revised, put
    // on a schedule — and none of it passes through `agent`. The tab showing it re-reads
    // on this, which is why the announcement carries no payload and no tool names
    // (`agentActivity.ts`).
    const api = createFakeApi();
    const heard: number[] = [];
    const activity = {
      subscribe: () => () => {},
      turnFinished: () => heard.push(1),
    };
    const store = createAgentChatStore(
      null,
      api,
      async () => null,
      () => null,
      fakeDrawings(),
      activity,
    );

    store.send("build me a team of two");

    await waitFor(() => expect(store.getSnapshot().turn).toBeNull());
    expect(heard).toHaveLength(1);
  });

  it("says it even when the turn broke, because a tool may have written before it did", async () => {
    const api = createFakeApi();
    api.script = [
      { kind: "fragment", text: "half a th" },
      { kind: "error", message: "the stream broke" },
    ];
    const heard: number[] = [];
    const activity = {
      subscribe: () => () => {},
      turnFinished: () => heard.push(1),
    };
    const store = createAgentChatStore(
      null,
      api,
      async () => null,
      () => null,
      fakeDrawings(),
      activity,
    );

    store.send("create the team and then fall over");

    await waitFor(() => expect(heard).toHaveLength(1));
  });
});


/** A turn that says one fragment and then waits, so a test can act while it is genuinely
 *  in flight. `ending` is what it says once released. The module's own transcript is
 *  recorded through `recordExchange`'s twin on the fake, so the reload afterwards shows
 *  what a real one would. */
function holdAfterFirstFragment(
  api: FakeApi,
  ending: AgentStreamEvent,
): { api: FakeApi; release: () => void } {
  let release = (): void => {};
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  async function* holding(): AsyncGenerator<AgentStreamEvent> {
    yield { kind: "fragment", text: "half an " };
    await held;
    yield ending;
  }
  return {
    api: {
      ...api,
      async sendMessage(id: number, content: string, signal: AbortSignal) {
        // Through the real fake first, so the transcript it keeps has the operator's
        // message in it and the reload after the turn is not empty.
        await api.sendMessage(id, content, signal);
        return holding();
      },
    },
    release: () => release(),
  };
}

describe("createAgentChatStore — stopping a turn", () => {
  it("asks the module to stop and marks nothing itself", async () => {
    // `terminal-agent-chat` spec, "Operator zatrzymuje trwającą odpowiedź" — the ending
    // comes from the module, on the stream and in the transcript. The store's own job is
    // to ask.
    const api = createFakeApi();
    const held = holdAfterFirstFragment(api, { kind: "stopped" });
    const store = createAgentChatStore(null, held.api);

    store.send("hello");
    await waitFor(() => expect(store.getSnapshot().turn?.status).toBe("streaming"));

    store.stop();
    await waitFor(() => expect(api.stopped).toHaveLength(1));
    // Still running as far as this side is concerned: nothing was marked on a promise.
    expect(store.getSnapshot().turn).not.toBeNull();

    held.release();
    await waitFor(() => expect(store.getSnapshot().turn).toBeNull());
    // And the composer is usable again — a stopped turn is a finished turn.
    expect(store.getSnapshot().transcriptStatus).toBe("ready");
  });

  it("does nothing when no turn is running", async () => {
    const api = createFakeApi();
    const store = createAgentChatStore(null, api);

    store.stop();
    await Promise.resolve();

    expect(api.stopped).toEqual([]);
  });

  it("says so when the module refuses the stop, and marks nothing", async () => {
    // `terminal-agent-chat` spec, "Moduł nie przyjął zatrzymania"
    const api = createFakeApi();
    api.failStopTurn = true;
    // The turn carries on to its own ending, which is the point: a refused stop stops
    // nothing.
    const held = holdAfterFirstFragment(api, { kind: "complete", incomplete: false });
    const store = createAgentChatStore(null, held.api);

    store.send("hello");
    await waitFor(() => expect(store.getSnapshot().turn?.status).toBe("streaming"));
    store.stop();

    await waitFor(() => expect(toastStore.getSnapshot()).toHaveLength(1));
    expect(toastStore.getSnapshot()[0].title).toMatch(/could not be stopped/i);

    held.release();
    await waitFor(() => expect(store.getSnapshot().turn).toBeNull());
    const reply = store.getSnapshot().messages.at(-1)!;
    expect(reply.stopped).toBe(false);
  });

  it("carries the module's own stopped mark into the transcript", async () => {
    const api = createFakeApi();
    const session = api.seed("earlier", "luna");
    api.transcripts.set(session.id, [
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
        content: "half an ",
        modelId: "luna",
        promptVersion: "v1",
        incomplete: true,
        stopped: true,
        createdAt: 0,
        toolCalls: [],
      },
    ]);
    const store = createAgentChatStore(null, api);

    store.openSession(session.id);
    await waitFor(() => expect(store.getSnapshot().messages).toHaveLength(2));

    const reply = store.getSnapshot().messages[1];
    expect(reply.incomplete).toBe(true);
    expect(reply.stopped).toBe(true);
  });
});


describe("createAgentChatStore — the width the operator sets", () => {
  const WIDTH_KEY = "terminal.agentChat.width.v1";
  // Wide enough that the bounds under test are the ones being asked about, not the
  // window's.
  const WINDOW = 1600;

  it("starts at the width the panel always had, with nothing stored", () => {
    const store = createAgentChatStore(memoryStorage(), createFakeApi());

    expect(store.getSnapshot().width).toBe(DEFAULT_PANEL_WIDTH);
  });

  it("remembers a width across a new store, which is what a reload is", () => {
    const storage = memoryStorage();
    const first = createAgentChatStore(storage, createFakeApi());

    first.setWidth(600, WINDOW);
    expect(first.getSnapshot().width).toBe(600);
    expect(storage.getItem(WIDTH_KEY)).toBe("600");

    const second = createAgentChatStore(storage, createFakeApi());
    expect(second.getSnapshot().width).toBe(600);
  });

  it("keeps the width through collapsing and expanding again", () => {
    const store = createAgentChatStore(memoryStorage(), createFakeApi());

    store.setWidth(700, WINDOW);
    store.setExpanded(false);
    store.setExpanded(true);

    expect(store.getSnapshot().width).toBe(700);
  });

  it("stops at both bounds rather than following the drag", () => {
    const store = createAgentChatStore(memoryStorage(), createFakeApi());

    store.setWidth(10, WINDOW);
    expect(store.getSnapshot().width).toBe(MIN_PANEL_WIDTH);

    store.setWidth(WINDOW * 2, WINDOW);
    expect(store.getSnapshot().width).toBe(maxPanelWidth(WINDOW));
    // The tab beside it keeps a usable share of the screen, which is the whole reason
    // there is an upper bound at all.
    expect(store.getSnapshot().width).toBeLessThan(WINDOW);
  });

  it("brings a width saved on a wider screen inside this window's bounds", () => {
    // `terminal-agent-chat` spec, "Okno węższe niż zapamiętana szerokość"
    const storage = memoryStorage({ [WIDTH_KEY]: "1400" });
    const store = createAgentChatStore(storage, createFakeApi());

    // The store reads `window.innerWidth`, which jsdom fixes at 1024.
    expect(store.getSnapshot().width).toBe(maxPanelWidth(window.innerWidth));
  });

  it("falls back to the default when the stored value is not a width", () => {
    const store = createAgentChatStore(memoryStorage({ [WIDTH_KEY]: "wide" }), createFakeApi());

    expect(store.getSnapshot().width).toBe(DEFAULT_PANEL_WIDTH);
  });

  it("survives a storage that throws", () => {
    const throwing: Storage = {
      ...memoryStorage(),
      getItem: () => {
        throw new Error("Safari private mode");
      },
      setItem: () => {
        throw new Error("Safari private mode");
      },
    };
    const store = createAgentChatStore(throwing, createFakeApi());

    expect(store.getSnapshot().width).toBe(DEFAULT_PANEL_WIDTH);
    store.setWidth(600, WINDOW);
    expect(store.getSnapshot().width).toBe(600);
  });
});
