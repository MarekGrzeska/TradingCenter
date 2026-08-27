/**
 * A store rather than a context, for the reason `gridStore` is one: the panel is mounted once in `Shell` and must
 * survive a tab switch. The transcript and the session list are the module's — only the furniture is kept here.
 */

import { safeLocalStorage } from "../data/storage";
import { agentActivity, type AgentActivityStore } from "./agentActivity";
import {
  agentApi,
  type AgentApi,
  type AgentMessage,
  type AgentModel,
  type AgentSession,
  type AgentChartSnapshot,
  type AgentToolCall,
  type ChatRole,
} from "./agentApi";
import {
  activeChartSnapshot,
  describeChartControl,
  syncAgentChart,
  type ChartControlResult,
} from "./chartControl";
import {
  describeDrawingsChange,
  drawingsStore,
  type DrawingsChange,
  type DrawingsStore,
} from "./drawingsStore";
import type { AgentStreamEvent } from "./stream";
import { showToast } from "../ui/toastStore";

export type { ChatRole };

/** Versioned, like `terminal.grid.v1`: a future shape change misses cleanly. Carries only
 *  the collapse bit, as it always has — design.md's Migration Plan commits to exactly
 *  that surviving unchanged. */
export const STORAGE_KEY = "terminal.agentChat.v1";

/** Which conversation was open, kept apart from `STORAGE_KEY` rather than folded into
 *  it: the collapse bit is a string enum that already shipped, and giving it a sibling
 *  key is a smaller change than restructuring what a checkout already has stored. */
const ACTIVE_SESSION_KEY = "terminal.agentChat.session.v1";

/** How wide the operator dragged the panel, in pixels. Its own key for the same reason
 *  the session id has one: `STORAGE_KEY` holds a string enum that already shipped. */
const WIDTH_KEY = "terminal.agentChat.width.v1";

/** The width the panel had when it was one number in the markup (`w-115`), and what a
 *  checkout that has never dragged it still gets. */
export const DEFAULT_PANEL_WIDTH = 460;

/** Below this the header's own row — the two buttons, the model name and the collapse
 *  control — stops fitting, and the panel is a column of wrapped words. */
export const MIN_PANEL_WIDTH = 320;

/** The other end is a fraction of the window rather than a number: a stopping point
 *  chosen on one screen is arbitrary on every other, and what has to stay true is that
 *  the tab beside the panel is still worth looking at. */
const MAX_PANEL_FRACTION = 0.6;

/** The widest the panel may be right now. Asked at every point the width is set — the
 *  operator drags, the window resizes, or a width saved on a larger screen is read back
 *  on a smaller one (`terminal-agent-chat` spec, "Okno węższe niż zapamiętana
 *  szerokość"). */
export function maxPanelWidth(windowWidth: number): number {
  return Math.max(MIN_PANEL_WIDTH, Math.round(windowWidth * MAX_PANEL_FRACTION));
}

export function clampPanelWidth(width: number, windowWidth: number): number {
  return Math.min(Math.max(width, MIN_PANEL_WIDTH), maxPanelWidth(windowWidth));
}

export interface ChatMessage {
  /** A number once the module has assigned one; a `local-`-prefixed string for a
   *  message that exists only on screen — the operator's turn before the module has
   *  answered, or a reply reconstructed from what arrived after a break that could not
   *  be reloaded. Replaced by the module's own id the next time the transcript reloads. */
  id: number | string;
  role: ChatRole;
  text: string;
  /** What the agent read on the way to this reply, in the order it read it. Empty for an
   *  operator's message and for a reply that asked nothing. */
  toolCalls: AgentToolCall[];
  /** Mirrors the module's own `incomplete` — a reply cut short by a broken stream, or
   *  reconstructed locally because the module could not be reached to confirm it
   *  (`terminal-agent-chat` spec, "Odpowiedź niepełna MUST być oznaczona jako
   *  niepełna"). */
  incomplete: boolean;
  /** Incomplete because the operator said stop, rather than because anything broke. The
   *  panel says two different things about the two, and only the module can tell them
   *  apart (`terminal-agent-chat` spec, "Odpowiedź zatrzymana nie jest błędem"). */
  stopped: boolean;
}

/** The turn in flight, or the one that just failed before anything was persisted.
 *  Nothing here duplicates a finished reply — that lives in `messages`, reloaded from
 *  the module, the moment it is known. */
export type TurnState =
  /** Calls carried on every in-flight status, not only on `streaming`: a turn that opens
   *  with a round of tools makes them before the model has written a word, and dropping
   *  them on the way from `waiting` to `streaming` would blank the panel at exactly the
   *  moment it started saying something. */
  | { status: "waiting"; toolCalls: AgentToolCall[] }
  | { status: "streaming"; text: string; toolCalls: AgentToolCall[] }
  /** The module never accepted this turn — no operator message, no reply, nothing
   *  reloadable. `terminal-agent-chat` spec, "MUST NOT pokazywać wypowiedzi agenta,
   *  która nie powstała": the panel says so in words, not with an empty bubble. */
  | { status: "unreachable"; message: string };

export type LoadStatus = "loading" | "ready" | "unreachable";

export interface AgentChatState {
  expanded: boolean;
  /** How wide the panel stands, in pixels — the operator's own measure, kept between
   *  reloads and across collapsing (`terminal-agent-chat` spec, "Operator ustawia
   *  szerokość panelu"). */
  width: number;
  sessions: AgentSession[];
  sessionsStatus: LoadStatus;
  activeSessionId: number | null;
  messages: ChatMessage[];
  transcriptStatus: LoadStatus;
  /** Calls this conversation made that no reply claimed — a turn that died with something
   *  in flight. Almost always empty; when it is not, it is the only place on screen that an
   *  order of unknown outcome appears (`agent-trading` spec). Shown at the end of the
   *  transcript rather than beside a reply, because there is no reply they belong to. */
  unclaimedToolCalls: AgentToolCall[];
  turn: TurnState | null;
  models: AgentModel[];
  modelsStatus: LoadStatus;
  /** The model the next turn in the active conversation runs on — an existing
   *  session's own `currentModelId` once one is open, or the pick that will become the
   *  first session's model once one exists. `null` only until the catalogue loads. */
  selectedModelId: string | null;
  /** What the agent last did to the chart, in one sentence, or null when it has not
   *  touched it. A chart that changes on its own without a word reads as a fault
   *  (`terminal-agent-chat` spec, "Panel mówi, że wykres zmienił agent"). */
  chartNotice: string | null;
}

export interface AgentChatStore {
  subscribe(listener: () => void): () => void;
  getSnapshot(): AgentChatState;
  setExpanded(expanded: boolean): void;
  /** Sets the panel's width, brought inside the bounds for the window it is being asked
   *  about. Called on every drag frame, so it commits only when the clamped value
   *  actually changed. */
  setWidth(width: number, windowWidth?: number): void;
  /** Loads what an open panel needs and has not got. Called by the panel on mount —
   *  after sign-in has resolved, which construction is not. Safe to call repeatedly. */
  ensureLoaded(): void;
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
  /** Asks the module to end the turn in flight. Marks nothing itself: the ending arrives
   *  on the stream and the reply from the transcript, the same as every other turn. A
   *  no-op when nothing is running. */
  stop(): void;
}

type Storage = Pick<globalThis.Storage, "getItem" | "setItem">;

/** The window this terminal is running in, or a wide-enough stand-in where there is none
 *  — a test constructing the store outside a DOM is asking about widths, not about
 *  windows. */
function currentWindowWidth(): number {
  return typeof window === "undefined" ? DEFAULT_PANEL_WIDTH / MAX_PANEL_FRACTION : window.innerWidth;
}

function loadExpanded(storage: Storage | null): boolean {
  if (!storage) return false;
  try {
    return storage.getItem(STORAGE_KEY) === "expanded";
  } catch {
    // A storage that throws (Safari private mode) must not stop the terminal starting.
    return false;
  }
}

function loadWidth(storage: Storage | null, windowWidth: number): number {
  if (!storage) return DEFAULT_PANEL_WIDTH;
  try {
    const raw = Number(storage.getItem(WIDTH_KEY));
    // A key that was never written, or written by hand into something that is not a number, is the same
    // case as no storage at all — the default, not a panel one pixel wide.
    if (!Number.isFinite(raw) || raw <= 0) return DEFAULT_PANEL_WIDTH;
    return clampPanelWidth(raw, windowWidth);
  } catch {
    return DEFAULT_PANEL_WIDTH;
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
    stopped: message.stopped,
    toolCalls: message.toolCalls,
  };
}

export function createAgentChatStore(
  storage: Storage | null = safeLocalStorage(),
  api: AgentApi = agentApi,
  // Injected rather than imported at the call site so a test can watch it without a
  // grid, an archive and a localStorage behind it.
  syncChart: () => Promise<ChartControlResult | null> = () => syncAgentChart(),
  // What the terminal is drawing as the question is asked. Read at send time, not at
  // construction: the operator may have changed slots since the panel opened.
  chartSnapshot: () => AgentChartSnapshot | null = activeChartSnapshot,
  // The objects the agent leaves on an instrument. Read the same way and at the same moments as its chart
  // commands, and said in the same sentence — one channel, not two.
  drawings: DrawingsStore = drawingsStore,
  // Everything else a turn may have changed, in a module this store knows nothing about: a chat can create
  // and run a team without any of it passing through `agent`.
  activity: AgentActivityStore = agentActivity,
): AgentChatStore {
  let state: AgentChatState = {
    expanded: loadExpanded(storage),
    width: loadWidth(storage, currentWindowWidth()),
    sessions: [],
    sessionsStatus: "loading",
    activeSessionId: loadActiveSessionId(storage),
    messages: [],
    unclaimedToolCalls: [],
    transcriptStatus: "ready",
    turn: null,
    models: [],
    modelsStatus: "loading",
    selectedModelId: null,
    chartNotice: null,
  };
  let nextLocalId = 1;
  let transcriptSeq = 0;
  // Not "has the panel been opened before" — that was the old gate, and a load which failed under it never
  // got a second chance. These say only "a request is already out".
  let modelsInFlight = false;
  let sessionsInFlight = false;
  let chartSyncInFlight = false;
  // Which conversation's transcript is actually on screen. `transcriptStatus` cannot say: it starts
  // "ready", because an empty panel is not one that is loading.
  let transcriptFor: number | null = null;
  const listeners = new Set<() => void>();

  function commit(next: AgentChatState): void {
    state = next;
    for (const listener of listeners) listener();
  }

  function setWidth(width: number, windowWidth: number = currentWindowWidth()): void {
    const next = clampPanelWidth(width, windowWidth);
    if (next === state.width) return;
    try {
      storage?.setItem(WIDTH_KEY, String(next));
    } catch {
      // Full or unavailable quota — the panel simply won't remember past this session,
      // the same as the collapse bit.
    }
    commit({ ...state, width: next });
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
    if (modelsInFlight) return;
    modelsInFlight = true;
    commit({ ...state, modelsStatus: "loading" });
    try {
      const models = await api.listModels(new AbortController().signal);
      commit({
        ...state,
        models,
        modelsStatus: "ready",
        // The cheapest catalogue entry is the module's own default too. Only filled in when nothing is
        // picked yet: opening an existing session sets this from that session's own model.
        selectedModelId: state.selectedModelId ?? models[0]?.id ?? null,
      });
    } catch {
      commit({ ...state, modelsStatus: "unreachable" });
    } finally {
      modelsInFlight = false;
    }
  }

  async function loadSessions(): Promise<void> {
    if (sessionsInFlight) return;
    sessionsInFlight = true;
    try {
      const sessions = await api.listSessions(new AbortController().signal);
      commit({ ...state, sessions, sessionsStatus: "ready" });
    } catch {
      commit({ ...state, sessionsStatus: "unreachable" });
    } finally {
      sessionsInFlight = false;
    }
  }

  /** Read alongside the transcript, and never allowed to fail it. An empty list is both "there are none"
   *  and "we could not tell", which is acceptable only because the ordinary answer is empty. */
  async function readUnclaimed(id: number): Promise<AgentToolCall[]> {
    try {
      return await api.getUnclaimedToolCalls(id, new AbortController().signal);
    } catch {
      return [];
    }
  }

  async function loadMessages(id: number): Promise<void> {
    const seq = ++transcriptSeq;
    transcriptFor = id;
    commit({ ...state, messages: [], unclaimedToolCalls: [], transcriptStatus: "loading" });
    try {
      const [raw, unclaimed] = await Promise.all([
        api.getMessages(id, new AbortController().signal),
        readUnclaimed(id),
      ]);
      if (seq !== transcriptSeq || id !== state.activeSessionId) return;
      commit({
        ...state,
        messages: raw.map(toChatMessage),
        unclaimedToolCalls: unclaimed,
        transcriptStatus: "ready",
      });
    } catch {
      transcriptFor = null; // so a retry is possible — this one showed nothing
      if (seq !== transcriptSeq || id !== state.activeSessionId) return;
      commit({ ...state, transcriptStatus: "unreachable" });
    }
  }

  /** Called once a turn has ended, to bring the transcript back to what the module holds. Only when the
   *  reload itself fails does the accumulated text show as a local, unconfirmed bubble. */
  async function finishTurn(
    sessionId: number,
    accumulated: string,
    calls: AgentToolCall[],
    errorMessage: string | null,
  ): Promise<void> {
    // A turn is the one moment the chart is most likely to have been set, so the read happens here rather
    // than on a timer. Not awaited: the two are independent.
    void syncChartCommands();
    // And the same moment for everything the agent may have written *outside* this module, which this
    // store cannot read and must not try to. Not awaited: a tab refreshing itself is nobody's turn to wait for.
    activity.turnFinished();

    const seq = ++transcriptSeq;
    let messages: ChatMessage[] | null = null;
    // A turn that broke is exactly when a call can be left unclaimed, so this reload is
    // the one that matters most for it.
    const unclaimed = await readUnclaimed(sessionId);
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
          stopped: false,
          // The module could not be asked what it holds, so the calls that arrived on the stream are the
          // only record on screen — dropping them would take away what explains a reply that broke off.
          toolCalls: calls,
        },
      ];
    }
    commit({
      ...state,
      messages,
      unclaimedToolCalls: unclaimed,
      transcriptStatus: "ready",
      turn: null,
    });
    void loadSessions();
    if (errorMessage) {
      // Said once, at the moment of the break — the bubble's own `incomplete` flag is what stays on screen
      // after this, so nothing here needs to persist in state.
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
    if (expanded) ensureLoaded();
  }

  /** Whatever the agent set while nobody was reading — on the way in, and after every turn. Never awaited
   *  by anything the operator waits for, and guarded against overlap: applying one command twice would
   *  rebuild every indicator series for nothing. */
  async function syncChartCommands(): Promise<void> {
    if (chartSyncInFlight) return;
    chartSyncInFlight = true;
    try {
      // Both reads, then one sentence. The drawing read is not conditional on the command read having
      // found anything: the agent may have drawn without setting the chart at all.
      let change: DrawingsChange = { added: 0, removed: 0 };
      const [command] = await Promise.all([
        syncChart(),
        drawings.refreshAll().then((result) => {
          change = result;
        }),
      ]);
      const notice = [describeChartControl(command), describeDrawingsChange(change)]
        .filter((sentence): sentence is string => sentence !== null)
        .join(" ");
      if (notice === "") return;
      commit({ ...state, chartNotice: notice });
    } finally {
      chartSyncInFlight = false;
    }
  }

  /**
   * Safe to call repeatedly, and called from the panel's mount rather than this module's construction: that ran
   * during `import`, before sign-in resolved, and the model picker read "unavailable" for the life of the page.
   */
  function ensureLoaded(): void {
    // Read whether or not the panel is open, so a command issued before the tab closed is not left waiting
    // on the operator opening it. The notice this leaves renders the moment they do.
    void syncChartCommands();
    if (!state.expanded) return;
    if (state.modelsStatus !== "ready") void loadModels();
    if (state.sessionsStatus !== "ready") void loadSessions();
    if (state.activeSessionId !== null && transcriptFor !== state.activeSessionId) {
      void loadMessages(state.activeSessionId);
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
      // Belongs to the conversation just left, not this one.
      chartNotice: null,
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
      unclaimedToolCalls: [],
      transcriptStatus: "ready",
      turn: null,
      selectedModelId: state.models[0]?.id ?? state.selectedModelId,
      // Belongs to the conversation just left, not this one.
      chartNotice: null,
    });
    persistActiveSessionId(null);
  }

  /**
   * Optimistic on neither count: the row changes only once the module has agreed. A list that renames
   * itself and then silently reverts is worse than one that pauses.
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
   * Removing the conversation currently on screen leaves the panel on a new, empty one — keeping the
   * transcript visible would be showing a rozmowa the module now answers 404 for.
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
              unclaimedToolCalls: [],
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
      stopped: false,
      toolCalls: [],
    };
    commit({
      ...state,
      messages: [...state.messages, operatorMessage],
      turn: { status: "waiting", toolCalls: [] },
      // Said once, about the turn that set it — carrying it into the next question would
      // describe a chart the operator may since have changed by hand.
      chartNotice: null,
    });

    let sessionId = state.activeSessionId;
    let accumulated = "";
    let calls: AgentToolCall[] = [];

    try {
      if (sessionId === null) {
        const session = await api.createSession(state.selectedModelId, new AbortController().signal);
        sessionId = session.id;
        commit({ ...state, activeSessionId: sessionId, selectedModelId: session.currentModelId });
        persistActiveSessionId(sessionId);
      }

      let events: AsyncGenerator<AgentStreamEvent>;
      try {
        events = await api.sendMessage(
          sessionId,
          trimmed,
          new AbortController().signal,
          chartSnapshot(),
        );
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
            commit({ ...state, turn: { status: "streaming", text: accumulated, toolCalls: calls } });
          } else if (event.kind === "toolCall") {
            calls = [...calls, event.call];
            // Still `waiting` until the first fragment: a round of tools can resolve before the model has
            // written a word, and claiming `streaming` with no text would show an empty bubble.
            commit({
              ...state,
              turn:
                accumulated === ""
                  ? { status: "waiting", toolCalls: calls }
                  : { status: "streaming", text: accumulated, toolCalls: calls },
            });
          } else if (event.kind === "complete") {
            await finishTurn(sessionId, accumulated, calls, event.incomplete ? "reply marked incomplete" : null);
            return;
          } else if (event.kind === "error") {
            await finishTurn(sessionId, accumulated, calls, event.message);
            return;
          } else if (event.kind === "stopped") {
            // Nothing said in the console and nothing kept in state: this ending is not a fault, and the
            // reply reloaded below carries its own mark.
            await finishTurn(sessionId, accumulated, calls, null);
            return;
          }
        }
        // The body ended with neither `complete` nor `error` — a dropped connection. The turn was accepted,
        // so this is the same recovery as a mid-stream error, not a "nothing happened" refusal.
        await finishTurn(sessionId, accumulated, calls, "the connection ended before the reply finished");
      } catch (cause) {
        await finishTurn(sessionId, accumulated, calls, describeError(cause));
      }
    } catch (cause) {
      // Creating the session itself failed — nothing was accepted for this turn.
      commit({ ...state, turn: { status: "unreachable", message: describeError(cause) } });
    }
  }

  function stop(): void {
    const sessionId = state.activeSessionId;
    if (sessionId === null || !turnInFlight()) return;

    void (async () => {
      try {
        await api.stopTurn(sessionId, new AbortController().signal);
      } catch (cause) {
        // The turn is still running and will still answer. Marking the reply stopped here would put a word on
        // screen the module never agreed to (`terminal-agent-chat` spec, "Moduł nie przyjął zatrzymania").
        showToast({
          key: "agent:stop",
          severity: "error",
          title: "the turn could not be stopped",
          detail: describeError(cause),
        });
      }
    })();
  }

  // A checkout that reloads with the panel already expanded gets no click on the rail button, and the load that
  // click would cause used to run at construction — during `import`. `AgentChat` calls `ensureLoaded` on mount.

  return {
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    getSnapshot: () => state,
    setExpanded,
    setWidth,
    ensureLoaded,
    toggle() {
      setExpanded(!state.expanded);
    },
    openSession,
    newSession,
    renameSession,
    deleteSession,
    setModel,
    stop,
    send(text) {
      void send(text);
    },
  };
}

export const agentChatStore = createAgentChatStore();
