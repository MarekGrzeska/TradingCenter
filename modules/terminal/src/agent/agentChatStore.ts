/**
 * The agent chat's own state, in a store rather than a context for the same reason
 * `gridStore` is one: the panel is mounted once in `Shell`, beside the router outlet and
 * not inside it, so nothing in a tab has to provide anything for it to open.
 *
 * Expansion is the only thing that decides whether the panel is on screen — there is no
 * per-tab visibility and no route of its own. A tab switch re-renders the outlet; the
 * panel is a sibling of it and does not remount.
 *
 * Mockup: the transcript is local and the replies are canned. Nothing here talks to an
 * agent runtime yet, and the shape below is deliberately the smallest one a real
 * transport could later fill (append operator turn → append agent turn).
 */

/** Versioned, like `terminal.grid.v1`: a future shape change misses cleanly. */
export const STORAGE_KEY = "terminal.agentChat.v1";

export type ChatRole = "operator" | "agent";

export interface ChatMessage {
  id: number;
  role: ChatRole;
  text: string;
}

export interface AgentChatState {
  expanded: boolean;
  messages: readonly ChatMessage[];
}

export interface AgentChatStore {
  subscribe(listener: () => void): () => void;
  getSnapshot(): AgentChatState;
  setExpanded(expanded: boolean): void;
  toggle(): void;
  /** Blank input is ignored rather than rejected — an accidental Enter is not an error
   *  worth a message about. */
  send(text: string): void;
}

type Storage = Pick<globalThis.Storage, "getItem" | "setItem">;

/** What the panel shows before anything is typed. An empty transcript would make the
 *  mockup read as broken rather than as unwired. */
function seedMessages(): ChatMessage[] {
  return [
    {
      id: 1,
      role: "agent",
      text: "Mockup — no agent is wired up behind this panel yet. The layout is what is up for review: it docks right, spans the full height, and pushes the tab content aside rather than covering it.",
    },
  ];
}

/** Canned answer, so sending a message shows the two-turn rhythm the real thing will have. */
const CANNED_REPLY =
  "Still a mockup: this reply is hard-coded. A real turn would go to the agent runtime and stream back here.";

function loadExpanded(storage: Storage | null): boolean {
  if (!storage) return false;
  try {
    return storage.getItem(STORAGE_KEY) === "expanded";
  } catch {
    // A storage that throws (Safari private mode) must not stop the terminal starting.
    return false;
  }
}

export function createAgentChatStore(
  storage: Storage | null = safeLocalStorage(),
): AgentChatStore {
  let state: AgentChatState = { expanded: loadExpanded(storage), messages: seedMessages() };
  let nextId = state.messages.length + 1;
  const listeners = new Set<() => void>();

  function commit(next: AgentChatState): void {
    state = next;
    for (const listener of listeners) listener();
  }

  function setExpanded(expanded: boolean): void {
    if (expanded === state.expanded) return;
    try {
      // Persisted because the panel takes width from the charts: an operator who closed it
      // should not find it open again after a reload, nor the reverse.
      storage?.setItem(STORAGE_KEY, expanded ? "expanded" : "collapsed");
    } catch {
      // Full or unavailable quota — the panel simply won't remember past this session.
    }
    commit({ ...state, expanded });
  }

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

    send(text) {
      const trimmed = text.trim();
      if (!trimmed) return;
      const operator: ChatMessage = { id: nextId++, role: "operator", text: trimmed };
      const reply: ChatMessage = { id: nextId++, role: "agent", text: CANNED_REPLY };
      commit({ ...state, messages: [...state.messages, operator, reply] });
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
