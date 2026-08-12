import { describe, expect, it } from "vitest";
import { waitFor } from "@testing-library/react";
import { createAgentChatStore, STORAGE_KEY } from "./agentChatStore";
import type {
  AgentApi,
  AgentMessage,
  AgentModel,
  AgentSession,
} from "./agentApi";
import type { AgentStreamEvent } from "./stream";

const MODELS: AgentModel[] = [
  { id: "luna", displayName: "Luna", costRank: 1, inputRatePer1M: "0.2", outputRatePer1M: "1.2" },
  { id: "sol", displayName: "Sol", costRank: 3, inputRatePer1M: "5", outputRatePer1M: "30" },
];

async function* fromArray(events: AgentStreamEvent[]): AsyncGenerator<AgentStreamEvent> {
  yield* events;
}

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
        createdAt: 0,
      });
      const session = api.sessions.find((s) => s.id === id);
      // The module's own behaviour: a title appears once there has been an exchange.
      if (session && session.title === null) session.title = content.slice(0, 40);

      const text = api.script
        .filter((e): e is Extract<AgentStreamEvent, { kind: "fragment" }> => e.kind === "fragment")
        .map((e) => e.text)
        .join("");
      const broke = api.script.some((e) => e.kind === "error");
      if (text || !broke) {
        transcript.push({
          id: transcript.length + 1,
          role: "agent",
          content: text,
          modelId: session?.currentModelId ?? null,
          promptVersion: "v1",
          incomplete: broke,
          createdAt: 0,
        });
      }
      api.transcripts.set(id, transcript);
      return fromArray(api.script);
    },
    async usage() {
      return { totalCost: "0", byModel: [], bySession: [], byDay: [] };
    },
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

    expect(seenTurns).toContainEqual({ status: "waiting" });
    expect(seenTurns).toContainEqual({ status: "streaming", text: "why is " });
    expect(seenTurns).toContainEqual({ status: "streaming", text: "why is BTC flat" });

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
        createdAt: 0,
      },
    ]);
    const store = createAgentChatStore(null, api);
    store.setExpanded(true);
    await waitFor(() => expect(store.getSnapshot().sessionsStatus).toBe("ready"));

    store.openSession(older.id);
    await waitFor(() => expect(store.getSnapshot().transcriptStatus).toBe("ready"));

    expect(store.getSnapshot().messages).toEqual([
      { id: 1, role: "operator", text: "hello", incomplete: false },
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
      expect(store.getSnapshot().turn).toEqual({ status: "streaming", text: "still going" }),
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
        createdAt: 0,
      },
    ]);
    const storage = memoryStorage();
    const first = createAgentChatStore(storage, api);
    first.setExpanded(true);
    await waitFor(() => expect(first.getSnapshot().sessionsStatus).toBe("ready"));
    first.openSession(older.id);
    await waitFor(() => expect(first.getSnapshot().transcriptStatus).toBe("ready"));

    // A fresh store, as a reload would construct — reads back the same conversation
    // and loads it without anybody clicking it again.
    const second = createAgentChatStore(storage, api);
    expect(second.getSnapshot().activeSessionId).toBe(older.id);
    await waitFor(() => expect(second.getSnapshot().transcriptStatus).toBe("ready"));
    expect(second.getSnapshot().messages).toEqual([
      { id: 1, role: "operator", text: "hello", incomplete: false },
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
