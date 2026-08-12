/**
 * The agent chat's own state, in a store rather than a context for the same reason
 * `gridStore` is one: the panel is mounted once in `Shell`, beside the router outlet and
 * not inside it, so nothing in a tab has to provide anything for it to open — and it must
 * survive a tab switch untouched (`terminal-agent-chat` spec, "Panel należy do terminala,
 * nie do zakładki").
 *
 * The transcript and the session list are the module's, not this store's — every read
 * that matters (opening a conversation, finishing a turn) reloads from `agentApi` rather
 * than trusting what accumulated locally, so the browser is never the only place a
 * message lives (`terminal-agent-chat` spec, "przeglądarka MUST NOT być jego jedynym
 * źródłem"). Only the panel's own furniture — whether it is expanded, and which
 * conversation was open — is this store's to keep.
 */

import {
  agentApi,
  type AgentApi,
  type AgentMessage,
  type AgentModel,
  type AgentSession,
  type ChatRole,
} from "./agentApi";
import type { AgentStreamEvent } from "./stream";

export type { ChatRole };

/** Versioned, like `terminal.grid.v1`: a future shape change misses cleanly. Carries only
 *  the collapse bit, as it always has — design.md's Migration Plan commits to exactly
 *  that surviving unchanged. */
export const STORAGE_KEY = "terminal.agentChat.v1";

/** Which conversation was open, kept apart from `STORAGE_KEY` rather than folded into
 *  it: the collapse bit is a string enum that already shipped, and giving it a sibling
 *  key is a smaller change than restructuring what a checkout already has stored. */
const ACTIVE_SESSION_KEY = "terminal.agentChat.session.v1";

export interface ChatMessage {
  /** A number once the module has assigned one; a `local-`-prefixed string for a
   *  message that exists only on screen — the operator's turn before the module has
   *  answered, or a reply reconstructed from what arrived after a break that could not
   *  be reloaded. Replaced by the module's own id the next time the transcript reloads. */
  id: number | string;
  role: ChatRole;
  text: string;
  /** Mirrors the module's own `incomplete` — a reply cut short by a broken stream, or
   *  reconstructed locally because the module could not be reached to confirm it
   *  (`terminal-agent-chat` spec, "Odpowiedź niepełna MUST być oznaczona jako
   *  niepełna"). */
  incomplete: boolean;
}

/** The turn in flight, or the one that just failed before anything was persisted.
 *  Nothing here duplicates a finished reply — that lives in `messages`, reloaded from
 *  the module, the moment it is known. */
export type TurnState =
  | { status: "waiting" }
  | { status: "streaming"; text: string }
  /** The module never accepted this turn — no operator message, no reply, nothing
   *  reloadable. `terminal-agent-chat` spec, "MUST NOT pokazywać wypowiedzi agenta,
   *  która nie powstała": the panel says so in words, not with an empty bubble. */
  | { status: "unreachable"; message: string };

export type LoadStatus = "loading" | "ready" | "unreachable";

export interface AgentChatState {
  expanded: boolean;
  sessions: AgentSession[];
  sessionsStatus: LoadStatus;
  activeSessionId: number | null;
  messages: ChatMessage[];
  transcriptStatus: LoadStatus;
  turn: TurnState | null;
  models: AgentModel[];
  modelsStatus: LoadStatus;
  /** The model the next turn in the active conversation runs on — an existing
   *  session's own `currentModelId` once one is open, or the pick that will become the
   *  first session's model once one exists. `null` only until the catalogue loads. */
  selectedModelId: string | null;
}

export interface AgentChatStore {
  subscribe(listener: () => void): () => void;
  getSnapshot(): AgentChatState;
  setExpanded(expanded: boolean): void;
  toggle(): void;
  /** Opens a conversation from the list and loads its transcript from the module.
   *  A no-op while a turn is in flight — nothing here tracks more than one active
   *  conversation's turn at a time. */
  openSession(id: number): void;
  /** Clears the panel back to an empty, unsaved conversation — `terminal-agent-chat`
   *  spec, "rozmowa pojawia się na liście dopiero po pierwszej wymianie zdań". */
  newSession(): void;
  /** Gives a conversation the operator's own name, so a list of first questions becomes a
   *  list of subjects. Blank is ignored; the module trims and refuses the rest. */
  renameSession(id: number, title: string): void;
  /** Removes a conversation from the history. What it cost stays in the cost tab — the
   *  module keeps the usage rows (`agent-usage` spec, "Skasowanie rozmowy nie zmniejsza
   *  rachunku"). A no-op while a turn is in flight. */
  deleteSession(id: number): void;
  /** Picks the model for the active conversation, or for the one `send` will create if
   *  none is open yet. */
  setModel(modelId: string): void;
  /** Blank input is ignored rather than rejected — an accidental Enter is not an error
   *  worth a message about. */
  send(text: string): void;
}

type Storage = Pick<globalThis.Storage, "getItem" | "setItem">;

function loadExpanded(storage: Storage | null): boolean {
  if (!storage) return false;
  try {
    return storage.getItem(STORAGE_KEY) === "expanded";
  } catch {
    // A storage that throws (Safari private mode) must not stop the terminal starting.
    return false;
  }
}

function loadActiveSessionId(storage: Storage | null): number | null {
  if (!storage) return null;
  try {
    const raw = storage.getItem(ACTIVE_SESSION_KEY);
    if (!raw) return null;
    const id = Number(raw);
    return Number.isInteger(id) ? id : null;
  } catch {
    return null;
  }
}

function describeError(cause: unknown): string {
  return cause instanceof Error ? cause.message : "the agent module is not reachable";
}

function toChatMessage(message: AgentMessage): ChatMessage {
  return {
    id: message.id,
    role: message.role,
    text: message.content,
    incomplete: message.incomplete,
  };
}

export function createAgentChatStore(
  storage: Storage | null = safeLocalStorage(),
  api: AgentApi = agentApi,
): AgentChatStore {
  let state: AgentChatState = {
    expanded: loadExpanded(storage),
    sessions: [],
    sessionsStatus: "loading",
    activeSessionId: loadActiveSessionId(storage),
    messages: [],
    transcriptStatus: "ready",
    turn: null,
    models: [],
    modelsStatus: "loading",
    selectedModelId: null,
  };
  let nextLocalId = 1;
  let transcriptSeq = 0;
  let initialized = false;
  const listeners = new Set<() => void>();

  function commit(next: AgentChatState): void {
    state = next;
    for (const listener of listeners) listener();
  }

  function persistActiveSessionId(id: number | null): void {
    try {
      if (id === null) storage?.setItem(ACTIVE_SESSION_KEY, "");
      else storage?.setItem(ACTIVE_SESSION_KEY, String(id));
    } catch {
      // Full or unavailable quota — the panel simply won't remember past this session.
    }
  }

  function turnInFlight(): boolean {
    return state.turn?.status === "waiting" || state.turn?.status === "streaming";
  }

  async function loadModels(): Promise<void> {
    commit({ ...state, modelsStatus: "loading" });
    try {
      const models = await api.listModels(new AbortController().signal);
      commit({
        ...state,
        models,
        modelsStatus: "ready",
        // The cheapest catalogue entry is the module's own default too — see
        // `.env.example`'s `DEFAULT_MODEL_ID`. Only filled in when nothing is picked
        // yet: opening an existing session sets this from that session's own model.
        selectedModelId: state.selectedModelId ?? models[0]?.id ?? null,
      });
    } catch {
      commit({ ...state, modelsStatus: "unreachable" });
    }
  }

  async function loadSessions(): Promise<void> {
    try {
      const sessions = await api.listSessions(new AbortController().signal);
      commit({ ...state, sessions, sessionsStatus: "ready" });
    } catch {
      commit({ ...state, sessionsStatus: "unreachable" });
    }
  }

  async function loadMessages(id: number): Promise<void> {
    const seq = ++transcriptSeq;
    commit({ ...state, messages: [], transcriptStatus: "loading" });
    try {
      const raw = await api.getMessages(id, new AbortController().signal);
      if (seq !== transcriptSeq || id !== state.activeSessionId) return;
      commit({ ...state, messages: raw.map(toChatMessage), transcriptStatus: "ready" });
    } catch {
      if (seq !== transcriptSeq || id !== state.activeSessionId) return;
      commit({ ...state, transcriptStatus: "unreachable" });
    }
  }

  /** Called once a turn has ended, one way or another, to bring the transcript back to
   *  what the module actually holds. `errorMessage` set means the stream broke or the
   *  connection dropped mid-turn; the reload still happens first; only when the reload
   *  itself fails does the accumulated text get shown as a local, unconfirmed bubble
   *  (`terminal-agent-chat` spec, "to, co dotarło, zostaje na ekranie"). */
  async function finishTurn(
    sessionId: number,
    accumulated: string,
    errorMessage: string | null,
  ): Promise<void> {
    const seq = ++transcriptSeq;
    let messages: ChatMessage[] | null = null;
    try {
      const raw = await api.getMessages(sessionId, new AbortController().signal);
      messages = raw.map(toChatMessage);
    } catch {
      // Handled below — the module cannot confirm what it holds, so what arrived
      // locally is all there is left to show.
    }
    if (seq !== transcriptSeq || sessionId !== state.activeSessionId) return;

    if (!messages) {
      messages = [
        ...state.messages,
        {
          id: `local-${nextLocalId++}`,
          role: "agent",
          text: accumulated,
          incomplete: true,
        },
      ];
    }
    commit({ ...state, messages, transcriptStatus: "ready", turn: null });
    void loadSessions();
    if (errorMessage) {
      // Said once, at the moment of the break — the bubble's own `incomplete` flag is
      // what stays on screen after this (`terminal-agent-chat` spec, "MUST być
      // oznaczona jako niepełna"), so nothing here needs to persist in state.
      console.warn(`[agent] turn ended early: ${errorMessage}`);
    }
  }

  function setExpanded(expanded: boolean): void {
    if (expanded !== state.expanded) {
      try {
        storage?.setItem(STORAGE_KEY, expanded ? "expanded" : "collapsed");
      } catch {
        // Full or unavailable quota — the panel simply won't remember past this session.
      }
      commit({ ...state, expanded });
    }
    if (expanded && !initialized) {
      initialized = true;
      void loadModels();
      void loadSessions();
      if (state.activeSessionId !== null) void loadMessages(state.activeSessionId);
    }
  }

  function openSession(id: number): void {
    if (id === state.activeSessionId || turnInFlight()) return;
    const session = state.sessions.find((s) => s.id === id) ?? null;
    commit({
      ...state,
      activeSessionId: id,
      selectedModelId: session?.currentModelId ?? state.selectedModelId,
      turn: null,
    });
    persistActiveSessionId(id);
    void loadMessages(id);
  }

  function newSession(): void {
    if (state.activeSessionId === null && state.messages.length === 0) return;
    if (turnInFlight()) return;
    ++transcriptSeq; // orphans any in-flight loadMessages for the conversation just left
    commit({
      ...state,
      activeSessionId: null,
      messages: [],
      transcriptStatus: "ready",
      turn: null,
      selectedModelId: state.models[0]?.id ?? state.selectedModelId,
    });
    persistActiveSessionId(null);
  }

  /**
   * Optimistic on neither count: the row changes only once the module has agreed. A list
   * that renames itself and then silently reverts on a failed request is worse than one
   * that pauses — the operator would go on believing the name they can see.
   */
  function renameSession(id: number, title: string): void {
    const trimmed = title.trim();
    if (trimmed === "") return;
    const current = state.sessions.find((s) => s.id === id);
    if (current && current.title === trimmed) return;

    void (async () => {
      try {
        const session = await api.renameSession(id, trimmed, new AbortController().signal);
        commit({
          ...state,
          sessions: state.sessions.map((s) => (s.id === session.id ? session : s)),
        });
      } catch {
        // Refused or unreachable. The list still shows the old name, which is the one the
        // module still holds — nothing to undo, and nothing to claim.
        console.warn(`[agent] could not rename conversation ${id}`);
      }
    })();
  }

  /**
   * Removing the conversation currently on screen leaves the panel on a new, empty one —
   * the transcript it was showing is gone, and keeping it visible would be showing a
   * rozmowa the module now answers 404 for.
   */
  function deleteSession(id: number): void {
    if (turnInFlight()) return;

    void (async () => {
      try {
        await api.deleteSession(id, new AbortController().signal);
      } catch {
        console.warn(`[agent] could not delete conversation ${id}`);
        return;
      }
      const wasActive = state.activeSessionId === id;
      if (wasActive) ++transcriptSeq; // orphans any in-flight loadMessages for it
      commit({
        ...state,
        sessions: state.sessions.filter((s) => s.id !== id),
        ...(wasActive
          ? {
              activeSessionId: null,
              messages: [],
              transcriptStatus: "ready" as const,
              turn: null,
            }
          : {}),
      });
      if (wasActive) persistActiveSessionId(null);
    })();
  }

  function setModel(modelId: string): void {
    if (modelId === state.selectedModelId) return;
    const previous = state.selectedModelId;
    const sessionId = state.activeSessionId;
    commit({ ...state, selectedModelId: modelId });
    if (sessionId === null) return;

    void (async () => {
      try {
        const session = await api.setSessionModel(sessionId, modelId, new AbortController().signal);
        if (sessionId !== state.activeSessionId) return;
        commit({
          ...state,
          selectedModelId: session.currentModelId,
          sessions: state.sessions.map((s) => (s.id === session.id ? session : s)),
        });
      } catch {
        if (sessionId !== state.activeSessionId) return;
        // The module refused or could not be reached — the picker reverts rather than
        // claiming a model the conversation is not actually running on.
        commit({ ...state, selectedModelId: previous });
      }
    })();
  }

  async function send(text: string): Promise<void> {
    const trimmed = text.trim();
    if (trimmed === "" || turnInFlight()) return;

    const operatorMessage: ChatMessage = {
      id: `local-${nextLocalId++}`,
      role: "operator",
      text: trimmed,
      incomplete: false,
    };
    commit({ ...state, messages: [...state.messages, operatorMessage], turn: { status: "waiting" } });

    let sessionId = state.activeSessionId;
    let accumulated = "";

    try {
      if (sessionId === null) {
        const session = await api.createSession(state.selectedModelId, new AbortController().signal);
        sessionId = session.id;
        commit({ ...state, activeSessionId: sessionId, selectedModelId: session.currentModelId });
        persistActiveSessionId(sessionId);
      }

      let events: AsyncGenerator<AgentStreamEvent>;
      try {
        events = await api.sendMessage(sessionId, trimmed, new AbortController().signal);
      } catch (cause) {
        // Nothing accepted yet — no operator message, no turn, nothing to reload.
        commit({ ...state, turn: { status: "unreachable", message: describeError(cause) } });
        return;
      }

      try {
        for await (const event of events) {
          if (sessionId !== state.activeSessionId) return; // switched conversations mid-turn
          if (event.kind === "fragment") {
            accumulated += event.text;
            commit({ ...state, turn: { status: "streaming", text: accumulated } });
          } else if (event.kind === "complete") {
            await finishTurn(sessionId, accumulated, event.incomplete ? "reply marked incomplete" : null);
            return;
          } else if (event.kind === "error") {
            await finishTurn(sessionId, accumulated, event.message);
            return;
          }
        }
        // The body ended with neither `complete` nor `error` — a dropped connection.
        // The turn was accepted (we have a session and got at least the response
        // headers), so this is the same recovery as a mid-stream error, not a "nothing
        // happened" refusal.
        await finishTurn(sessionId, accumulated, "the connection ended before the reply finished");
      } catch (cause) {
        await finishTurn(sessionId, accumulated, describeError(cause));
      }
    } catch (cause) {
      // Creating the session itself failed — nothing was accepted for this turn.
      commit({ ...state, turn: { status: "unreachable", message: describeError(cause) } });
    }
  }

  // A checkout that reloads with the panel already expanded (`STORAGE_KEY` read as
  // "expanded" above) gets no click on the rail button to trigger the load that click
  // would otherwise cause — this is that trigger, run once at construction instead.
  if (state.expanded) setExpanded(true);

  return {
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    getSnapshot: () => state,
    setExpanded,
    toggle() {
      setExpanded(!state.expanded);
    },
    openSession,
    newSession,
    renameSession,
    deleteSession,
    setModel,
    send(text) {
      void send(text);
    },
  };
}

function safeLocalStorage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

export const agentChatStore = createAgentChatStore();
