import { useEffect, useRef, useState, useSyncExternalStore, type KeyboardEvent } from "react";

import { agentChatStore, type AgentChatState, type AgentChatStore, type ChatMessage } from "./agentChatStore";

/**
 * Mounted once in `Shell`, as a sibling of the router outlet rather than inside it: the
 * panel belongs to the terminal, not to a tab, so switching tabs neither hides it nor
 * remounts the conversation (`terminal-agent-chat` spec, "Panel należy do terminala, nie
 * do zakładki").
 *
 * Collapsed it is a rail on the right edge — a place, not a floating button, so the way in
 * is always in the same pixels whatever tab is on screen. Expanded it is a column in the
 * shell's flex row, which is what pushes the tab content aside instead of covering it; the
 * chart's ResizeObserver picks the new width up on its own.
 *
 * Whether the list of conversations or the transcript is on screen is this component's
 * own, unpersisted state — the store only remembers which conversation was open, not
 * which panel the operator was looking at when they last left.
 */
export function AgentChat({ store = agentChatStore }: { store?: AgentChatStore } = {}) {
  const state = useSyncExternalStore(store.subscribe, store.getSnapshot);
  const [view, setView] = useState<"chat" | "conversations">("chat");
  const turnInFlight = state.turn?.status === "waiting" || state.turn?.status === "streaming";

  if (!state.expanded) {
    return (
      // The whole rail is the button, not a control sitting on one: a full-height strip is
      // a target that cannot be missed at any window size, and there is nothing else in the
      // rail to aim at instead. The handle is centred rather than at the top so it reads as
      // the edge of a drawer — the shape says "pulls out", which the rotated word did not.
      <button
        type="button"
        onClick={() => store.setExpanded(true)}
        aria-label="Open agent chat"
        aria-expanded={false}
        aria-controls="agent-chat-panel"
        title="Agent chat"
        className="group flex w-9 shrink-0 cursor-pointer flex-col items-center justify-center border-l border-primary-line bg-panel transition-colors hover:bg-panel-strong"
      >
        <span
          aria-hidden
          className="flex flex-col items-center gap-1.5 rounded-l-md border border-r-0 border-primary-line bg-primary-soft px-1.5 py-3 text-primary transition-colors group-hover:bg-primary-strong group-hover:text-ink-inverse"
        >
          <AgentGlyph className="h-5 w-5" />
          <Chevron className="h-3 w-3" direction="left" />
        </span>
      </button>
    );
  }

  return (
    <aside
      id="agent-chat-panel"
      aria-label="Agent chat"
      className="flex w-96 shrink-0 flex-col border-l border-primary-line bg-panel"
    >
      <header className="flex h-12 shrink-0 items-center gap-2 border-b border-primary-line bg-panel-strong px-3">
        <AgentGlyph className="h-4 w-4 text-secondary" />
        <span className="text-sm font-semibold">Agent</span>
        <button
          type="button"
          onClick={() => setView(view === "chat" ? "conversations" : "chat")}
          aria-pressed={view === "conversations"}
          className="ml-2 rounded border border-border px-1.5 py-0.5 text-[11px] text-ink-muted hover:bg-panel hover:text-ink"
        >
          {view === "chat" ? "Conversations" : "Back to chat"}
        </button>
        <button
          type="button"
          onClick={() => {
            store.newSession();
            setView("chat");
          }}
          disabled={turnInFlight}
          title="New conversation"
          className="rounded border border-border px-1.5 py-0.5 text-[11px] text-ink-muted hover:bg-panel hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
        >
          New
        </button>
        <button
          type="button"
          onClick={() => store.setExpanded(false)}
          aria-label="Collapse agent chat"
          aria-expanded
          aria-controls="agent-chat-panel"
          className="ml-auto cursor-pointer rounded p-1.5 text-ink-muted transition-colors hover:bg-primary-soft hover:text-ink"
        >
          <Chevron className="h-4 w-4" direction="right" />
        </button>
      </header>

      <ModelPicker state={state} onChange={(modelId) => store.setModel(modelId)} />

      {view === "conversations" ? (
        <ConversationList
          state={state}
          onOpen={(id) => {
            store.openSession(id);
            setView("chat");
          }}
        />
      ) : (
        <>
          <Transcript messages={state.messages} turn={state.turn} />
          <Composer onSend={(text) => store.send(text)} disabled={turnInFlight} />
        </>
      )}
    </aside>
  );
}

/**
 * A speech bubble with a spark in it: what this panel holds is a conversation, and what
 * answers in it is not a person. Drawn rather than set as ✦ — a glyph is whatever the
 * machine's font decides, and lands at a different weight and baseline on each one.
 */
function AgentGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden className={className}>
      <path
        d="M5 4.75h14A1.75 1.75 0 0 1 20.75 6.5V15A1.75 1.75 0 0 1 19 16.75h-6.35L8.3 20.1v-3.35H5A1.75 1.75 0 0 1 3.25 15V6.5A1.75 1.75 0 0 1 5 4.75Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <path
        d="M12 7.1l1.2 2.55 2.55 1.2-2.55 1.2L12 14.6l-1.2-2.55-2.55-1.2 2.55-1.2L12 7.1Z"
        fill="currentColor"
      />
    </svg>
  );
}

function Chevron({ className, direction }: { className?: string; direction: "left" | "right" }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden className={className}>
      <path
        d={direction === "left" ? "M14.5 6.5 9 12l5.5 5.5" : "M9.5 6.5 15 12l-5.5 5.5"}
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/**
 * Built entirely from `state.models` — `terminal-agent-chat` spec, "terminal MUST NOT
 * nieść listy modeli we własnym kodzie". A catalogue that failed to load says so in
 * words rather than falling back to anything baked in here, which is the one way this
 * component could quietly start lying about what a session will actually run on.
 */
function ModelPicker({
  state,
  onChange,
}: {
  state: AgentChatState;
  onChange: (modelId: string) => void;
}) {
  if (state.modelsStatus === "unreachable") {
    return (
      <p className="border-b border-primary-line bg-panel px-3 py-2 text-xs text-critical">
        model picker unavailable — the catalogue could not be read
      </p>
    );
  }

  return (
    <div className="flex items-center gap-2 border-b border-primary-line bg-panel px-3 py-2">
      <label htmlFor="agent-model" className="text-[11px] text-ink-muted">
        Model
      </label>
      <select
        id="agent-model"
        value={state.selectedModelId ?? ""}
        onChange={(event) => onChange(event.target.value)}
        disabled={state.modelsStatus === "loading" || state.models.length === 0}
        className="flex-1 rounded border border-border bg-sunken px-1.5 py-1 text-xs text-ink disabled:cursor-not-allowed disabled:opacity-50"
      >
        {state.modelsStatus === "loading" && <option value="">Loading models…</option>}
        {state.models.map((model) => (
          <option key={model.id} value={model.id}>
            {model.displayName} — ${model.inputRatePer1k} in / ${model.outputRatePer1k} out per 1K
          </option>
        ))}
      </select>
    </div>
  );
}

/**
 * Newest-first, exactly as the module already orders `GET /sessions` — nothing here
 * re-sorts it. A conversation joins this list only once it has a title, which the
 * module only assigns after the first exchange (`terminal-agent-chat` spec, "rozmowa
 * pojawia się na liście dopiero po pierwszej wymianie zdań"): an empty, unsent new
 * conversation is never a row here.
 */
function ConversationList({
  state,
  onOpen,
}: {
  state: AgentChatState;
  onOpen: (id: number) => void;
}) {
  if (state.sessionsStatus === "unreachable") {
    return (
      <p className="px-3 py-4 text-xs text-critical">the conversation list could not be read</p>
    );
  }
  if (state.sessionsStatus === "loading") {
    return <p className="px-3 py-4 text-xs text-ink-muted">Reading conversations…</p>;
  }
  if (state.sessions.length === 0) {
    return <p className="px-3 py-4 text-xs text-ink-muted">No conversations yet.</p>;
  }

  return (
    <ul className="min-h-0 flex-1 overflow-y-auto">
      {state.sessions.map((session) => (
        <li key={session.id}>
          <button
            type="button"
            onClick={() => onOpen(session.id)}
            aria-current={session.id === state.activeSessionId}
            className={`w-full truncate px-3 py-2 text-left text-xs hover:bg-panel-strong ${
              session.id === state.activeSessionId ? "bg-panel-strong text-ink" : "text-ink-secondary"
            }`}
          >
            {session.title}
          </button>
        </li>
      ))}
    </ul>
  );
}

function Transcript({
  messages,
  turn,
}: {
  messages: readonly ChatMessage[];
  turn: AgentChatState["turn"];
}) {
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // `scrollTop`, not `scrollIntoView`: the latter is not implemented in jsdom, and the
    // container is the thing that scrolls anyway.
    const list = listRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [messages.length, turn]);

  return (
    <div
      ref={listRef}
      // `polite`: a reply arriving is worth announcing, never worth cutting off whatever
      // the operator is reading on the chart beside it.
      aria-live="polite"
      className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-3"
    >
      {messages.length === 0 && turn === null && (
        <p className="text-xs text-ink-faint">Ask the agent about the market on screen.</p>
      )}
      {messages.map((message) => (
        <Bubble key={message.id} message={message} />
      ))}
      {/* Before the first fragment the panel already says something happened — a
          message that vanished into a silent, unchanged screen is indistinguishable
          from one that was never sent (`terminal-agent-chat` spec, "Widać, że
          odpowiedź powstaje"). */}
      {turn?.status === "waiting" && <ThinkingBubble />}
      {turn?.status === "streaming" && (
        <Bubble message={{ id: "turn", role: "agent", text: turn.text, incomplete: false }} />
      )}
      {turn?.status === "unreachable" && (
        // Not a bubble: no agent reply happened, so nothing here impersonates one
        // (`terminal-agent-chat` spec, "MUST NOT pokazywać wypowiedzi agenta, która nie
        // powstała").
        <p className="rounded border border-critical/40 bg-critical/10 px-3 py-2 text-xs text-critical">
          the agent module is not reachable — {turn.message}
        </p>
      )}
    </div>
  );
}

function ThinkingBubble() {
  return (
    <div className="flex justify-start">
      <div className="rounded-lg rounded-bl-sm border border-border bg-panel-strong px-3 py-2 text-xs text-ink-faint">
        thinking…
      </div>
    </div>
  );
}

function Bubble({ message }: { message: ChatMessage }) {
  const operator = message.role === "operator";
  return (
    <div className={`flex ${operator ? "justify-end" : "justify-start"}`}>
      <div
        // Whose turn it is carries on shape and side as well as tint: the two bubbles differ
        // by alignment and by border, so they stay apart where the tint does not survive.
        className={`max-w-[85%] rounded-lg px-3 py-2 text-xs leading-relaxed wrap-break-word ${
          operator
            ? "rounded-br-sm bg-primary-soft text-ink"
            : message.incomplete
              ? "rounded-bl-sm border border-critical/50 bg-panel-strong text-ink-secondary"
              : "rounded-bl-sm border border-border bg-panel-strong text-ink-secondary"
        }`}
      >
        {message.text}
        {/* Never shown as a whole reply — the module's own `incomplete` flag, carried
            straight through (`terminal-agent-chat` spec, "Odpowiedź niepełna MUST być
            oznaczona jako niepełna, a nie pokazana jako całość"). */}
        {!operator && message.incomplete && (
          <div className="mt-1 text-[10px] font-semibold text-critical">⚠ incomplete — broke off</div>
        )}
      </div>
    </div>
  );
}

function Composer({
  onSend,
  disabled,
}: {
  onSend: (text: string) => void;
  disabled: boolean;
}) {
  const [draft, setDraft] = useState("");

  function submit(): void {
    if (disabled) return;
    onSend(draft);
    setDraft("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>): void {
    // Enter sends, Shift+Enter breaks the line: a chat box, not a form field. An operator
    // types far more one-line questions than paragraphs.
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <div className="shrink-0 border-t border-primary-line bg-panel-strong p-3">
      <textarea
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={onKeyDown}
        rows={2}
        disabled={disabled}
        aria-label="Message the agent"
        placeholder={disabled ? "Waiting for the reply…" : "Ask the agent…"}
        className="w-full resize-none rounded border border-primary-line bg-sunken px-2 py-1.5 text-xs text-ink placeholder:text-ink-faint focus:border-primary focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
      />
      <div className="mt-2 flex items-center gap-2">
        <span className="text-[10px] text-ink-faint">Enter sends · Shift+Enter new line</span>
        <button
          type="button"
          onClick={submit}
          disabled={disabled || draft.trim() === ""}
          className="ml-auto cursor-pointer rounded border border-primary-line bg-primary-soft px-2 py-1 text-xs text-ink transition-colors hover:bg-primary-strong hover:text-ink-inverse disabled:cursor-not-allowed disabled:border-border disabled:bg-transparent disabled:text-ink-faint"
        >
          Send
        </button>
      </div>
    </div>
  );
}
