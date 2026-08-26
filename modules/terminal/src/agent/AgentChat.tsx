import {
  Fragment,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";

import type { AgentToolCall } from "./agentApi";
import {
  agentChatStore,
  maxPanelWidth,
  MIN_PANEL_WIDTH,
  type AgentChatState,
  type AgentChatStore,
  type ChatMessage,
} from "./agentChatStore";
import { MessageBody } from "./MessageBody";
import { ToolCallEntry } from "./ToolCallEntry";
import { Button } from "../ui/Button";

/**
 * Mounted once in `Shell`, beside the router outlet rather than inside it: the panel belongs to the terminal, not
 * to a tab. Collapsed it is a rail, expanded a column in the shell's flex row — it pushes, never covers.
 */
export function AgentChat({ store = agentChatStore }: { store?: AgentChatStore } = {}) {
  const state = useSyncExternalStore(store.subscribe, store.getSnapshot);
  const [view, setView] = useState<"chat" | "conversations">("chat");
  const turnInFlight = state.turn?.status === "waiting" || state.turn?.status === "streaming";

  // The panel mounts after `main.tsx` has awaited `identity.initialize()`; the store is constructed during
  // `import`, which is before it. Asking here is what makes the first request carry a token.
  useEffect(() => {
    store.ensureLoaded();
  }, [store]);

  // A width chosen on a wide window is not a width on a narrow one. Re-asked rather than recomputed:
  // `setWidth` clamps against the window it is given and commits only when the answer moved.
  useEffect(() => {
    const reclamp = (): void => store.setWidth(store.getSnapshot().width);
    window.addEventListener("resize", reclamp);
    return () => window.removeEventListener("resize", reclamp);
  }, [store]);

  if (!state.expanded) {
    return (
      // The whole rail is the button, not a control sitting on one: a full-height strip cannot be missed
      // at any window size. The handle is centred so it reads as the edge of a drawer.
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
      // Width from the store rather than a Tailwind class: there is no class for a number the operator
      // chose, and building class names at runtime is what Tailwind's scanner cannot see.
      style={{ width: state.width }}
      className="relative flex shrink-0 flex-col border-l border-primary-line bg-panel"
    >
      <ResizeHandle width={state.width} onResize={(next) => store.setWidth(next)} />
      <header className="flex h-12 shrink-0 items-center gap-2 border-b border-primary-line bg-panel-strong px-3">
        <AgentGlyph className="h-4 w-4 text-secondary" />
        <span className="text-sm font-semibold">Agent</span>
        <Button
          tone="muted"
          size="2xs"
          className="ml-2"
          onClick={() => setView(view === "chat" ? "conversations" : "chat")}
          aria-pressed={view === "conversations"}
        >
          {view === "chat" ? "Conversations" : "Back to chat"}
        </Button>
        <Button
          tone="muted"
          size="2xs"
          onClick={() => {
            store.newSession();
            setView("chat");
          }}
          disabled={turnInFlight}
          title="New conversation"
        >
          New
        </Button>
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

      {view === "conversations" ? (
        <ConversationList
          state={state}
          onOpen={(id) => {
            store.openSession(id);
            setView("chat");
          }}
          onRename={(id, title) => store.renameSession(id, title)}
          onDelete={(id) => store.deleteSession(id)}
        />
      ) : (
        <>
          <Transcript
            messages={state.messages}
            turn={state.turn}
            unclaimedToolCalls={state.unclaimedToolCalls}
          />
          {state.chartNotice !== null && (
            // Above the composer rather than inside the transcript: the agent changed the chart, it did
            // not say something — and a chart that moves with no sentence anywhere reads as a fault.
            <p
              role="status"
              className="mx-3 mb-2 rounded border border-primary-line bg-primary-soft px-2 py-1 text-[11px] text-ink-secondary"
            >
              {state.chartNotice}
            </p>
          )}
          {/* The picker sits under the box it applies to: which model answers is a decision made while
              writing the question, so it belongs beside the writing rather than at the far end. */}
          <Composer
            onSend={(text) => store.send(text)}
            onStop={() => store.stop()}
            disabled={turnInFlight}
          >
            <ModelPicker state={state} onChange={(modelId) => store.setModel(modelId)} />
          </Composer>
        </>
      )}
    </aside>
  );
}

/**
 * The panel's own left edge, draggable. A `separator` because it is the one control here with no label. Absolutely
 * positioned over the border, so it takes the drag without taking layout — it would move the column it measures.
 */
function ResizeHandle({
  width,
  onResize,
}: {
  width: number;
  onResize: (width: number) => void;
}) {
  const max = maxPanelWidth(typeof window === "undefined" ? width : window.innerWidth);
  // Whether a drag is under way. Kept here rather than asked of the element: pointer capture is an
  // optimisation of the browser's and not every environment has it.
  const dragging = useRef(false);

  function onPointerDown(event: ReactPointerEvent<HTMLDivElement>): void {
    dragging.current = true;
    // Captured, so a pointer that leaves the handle mid-drag — which it does immediately,
    // because the panel is moving under it — keeps sending its moves here.
    event.currentTarget.setPointerCapture?.(event.pointerId);
    event.preventDefault();
  }

  function stopDragging(): void {
    dragging.current = false;
  }

  function onPointerMove(event: ReactPointerEvent<HTMLDivElement>): void {
    if (!dragging.current) return;
    // From the right edge of the window, not from a delta: the panel is the last column, so its width
    // *is* that distance, and a delta would drift by whatever the clamp swallowed last frame.
    onResize(window.innerWidth - event.clientX);
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>): void {
    const step = event.shiftKey ? 64 : 16;
    if (event.key === "ArrowLeft") onResize(width + step);
    else if (event.key === "ArrowRight") onResize(width - step);
    else if (event.key === "Home") onResize(MIN_PANEL_WIDTH);
    else if (event.key === "End") onResize(max);
    else return;
    event.preventDefault();
  }

  return (
    <div
      role="separator"
      aria-label="Resize agent chat"
      aria-orientation="vertical"
      aria-valuenow={width}
      aria-valuemin={MIN_PANEL_WIDTH}
      aria-valuemax={max}
      tabIndex={0}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={stopDragging}
      onPointerCancel={stopDragging}
      onKeyDown={onKeyDown}
      className="absolute top-0 -left-1 z-10 h-full w-2 cursor-col-resize hover:bg-primary/40 focus:bg-primary/40 focus:outline-none"
    />
  );
}

/**
 * A speech bubble with a spark in it: what this panel holds is a conversation, and what answers in it is
 * not a person. Drawn rather than set as a glyph, which lands at a different weight on each machine.
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
 * Built entirely from `state.models` — the terminal must not carry a list of its own. A catalogue that
 * failed to load says so in words rather than falling back to anything baked in here.
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
      <p className="mt-2 text-xs text-critical">
        model picker unavailable — the catalogue could not be read
      </p>
    );
  }

  return (
    <div className="mt-2 flex items-center gap-2">
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
            {model.displayName} — ${model.inputRatePer1M} in / ${model.outputRatePer1M} out per 1M
          </option>
        ))}
      </select>
    </div>
  );
}

/**
 * Newest-first, exactly as the module already orders it — nothing here re-sorts. A conversation joins this
 * list only once it has a title, so an empty, unsent new conversation is never a row.
 */
function ConversationList({
  state,
  onOpen,
  onRename,
  onDelete,
}: {
  state: AgentChatState;
  onOpen: (id: number) => void;
  onRename: (id: number, title: string) => void;
  onDelete: (id: number) => void;
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
        <ConversationRow
          key={session.id}
          session={session}
          active={session.id === state.activeSessionId}
          onOpen={onOpen}
          onRename={onRename}
          onDelete={onDelete}
        />
      ))}
    </ul>
  );
}

function ConversationRow({
  session,
  active,
  onOpen,
  onRename,
  onDelete,
}: {
  session: AgentChatState["sessions"][number];
  active: boolean;
  onOpen: (id: number) => void;
  onRename: (id: number, title: string) => void;
  onDelete: (id: number) => void;
}) {
  // Three states, not two: renaming and confirming a delete are both modes this row enters, and neither
  // may be reachable from the other — a stray Enter must not both rename and remove.
  const [mode, setMode] = useState<"idle" | "renaming" | "confirming">("idle");
  const [draft, setDraft] = useState(session.title ?? "");

  function commitRename(): void {
    onRename(session.id, draft);
    setMode("idle");
  }

  if (mode === "renaming") {
    return (
      <li className="flex items-center gap-1 px-2 py-1.5">
        <input
          // The row became a field on the operator's own click, so the caret has exactly
          // one sensible place to be.
          autoFocus
          value={draft}
          maxLength={120}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") commitRename();
            if (event.key === "Escape") setMode("idle");
          }}
          onBlur={commitRename}
          aria-label={`Rename ${session.title ?? "conversation"}`}
          className="min-w-0 flex-1 rounded border border-primary bg-sunken px-1.5 py-1 text-xs text-ink focus:outline-none"
        />
      </li>
    );
  }

  if (mode === "confirming") {
    return (
      <li className="flex items-center gap-2 bg-critical/10 px-3 py-2 text-xs">
        <span className="min-w-0 flex-1 truncate text-ink-secondary">Delete this conversation?</span>
        <button
          type="button"
          onClick={() => onDelete(session.id)}
          className="cursor-pointer rounded border border-critical/50 px-1.5 py-0.5 text-[11px] text-critical hover:bg-critical/20"
        >
          Delete
        </button>
        <Button
          tone="muted"
          size="2xs"
          onClick={() => setMode("idle")}
        >
          Keep
        </Button>
      </li>
    );
  }

  return (
    // `group` rather than always-on controls: a list read far more often than edited stays a list of
    // names. The two buttons are still in the tab order, so a keyboard reaches them without hovering.
    <li className="group flex items-center">
      <button
        type="button"
        onClick={() => onOpen(session.id)}
        aria-current={active}
        className={`min-w-0 flex-1 truncate px-3 py-2 text-left text-xs hover:bg-panel-strong ${
          active ? "bg-panel-strong text-ink" : "text-ink-secondary"
        }`}
      >
        {session.title}
      </button>
      <button
        type="button"
        onClick={() => {
          setDraft(session.title ?? "");
          setMode("renaming");
        }}
        aria-label={`Rename ${session.title ?? "conversation"}`}
        className="cursor-pointer px-1 py-2 text-[11px] text-ink-faint opacity-0 transition-opacity group-hover:opacity-100 focus:opacity-100 hover:text-ink"
      >
        Rename
      </button>
      <button
        type="button"
        onClick={() => setMode("confirming")}
        aria-label={`Delete ${session.title ?? "conversation"}`}
        className="cursor-pointer px-2 py-2 text-[11px] text-ink-faint opacity-0 transition-opacity group-hover:opacity-100 focus:opacity-100 hover:text-critical"
      >
        Delete
      </button>
    </li>
  );
}

function Transcript({
  messages,
  turn,
  unclaimedToolCalls,
}: {
  messages: readonly ChatMessage[];
  turn: AgentChatState["turn"];
  unclaimedToolCalls: readonly AgentToolCall[];
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
        // The calls come before the reply they produced, which is the order they happened
        // in — the agent read, then answered.
        <Fragment key={message.id}>
          {message.toolCalls.map((call) => (
            <ToolCallEntry key={`${message.id}-${call.roundIndex}-${call.position}`} call={call} />
          ))}
          <Bubble message={message} />
        </Fragment>
      ))}
      {unclaimedToolCalls.length > 0 && <UnclaimedCalls calls={unclaimedToolCalls} />}
          {/* Before the first fragment the panel already says something happened — a message that
              vanished into a silent screen is indistinguishable from one never sent. */}
          {/* The turn's own calls, shown as they arrive rather than at the end: a round of tools produces
              no text, and without them the panel says "thinking…" through the busiest part of the turn. */}
      {(turn?.status === "waiting" || turn?.status === "streaming") &&
        turn.toolCalls.map((call) => (
          <ToolCallEntry key={`turn-${call.roundIndex}-${call.position}`} call={call} />
        ))}
      {turn?.status === "waiting" && <ThinkingBubble />}
      {turn?.status === "streaming" && (
        <Bubble
          message={{
            id: "turn",
            role: "agent",
            text: turn.text,
            incomplete: false,
            stopped: false,
            toolCalls: [],
          }}
          streaming
        />
      )}
      {turn?.status === "unreachable" && (
        // Not a bubble: no agent reply happened, so nothing here impersonates one.
        <p className="rounded border border-critical/40 bg-critical/10 px-3 py-2 text-xs text-critical">
          the agent module is not reachable — {turn.message}
        </p>
      )}
    </div>
  );
}

/**
 * Calls the module kept that no reply claimed — a turn that died with something in flight, so they belong to no
 * exchange and sit under a heading at the end. One of these can be an order no sentence anywhere mentions.
 */
function UnclaimedCalls({ calls }: { calls: readonly AgentToolCall[] }) {
  return (
    <div className="flex flex-col gap-2 rounded border border-critical/40 bg-critical/5 p-2">
      <p className="text-[11px] text-critical">
        {calls.length === 1 ? "One call was" : `${calls.length} calls were`} left without a
        reply — the agent sent {calls.length === 1 ? "it" : "them"} and the turn ended before an
        answer was recorded. Check the account before asking again.
      </p>
      {calls.map((call) => (
        <ToolCallEntry
          key={`unclaimed-${call.roundIndex}-${call.position}-${call.name}`}
          call={call}
        />
      ))}
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

function Bubble({ message, streaming = false }: { message: ChatMessage; streaming?: boolean }) {
  const operator = message.role === "operator";
  return (
    <div className={`flex ${operator ? "justify-end" : "justify-start"}`}>
      <div
        // Whose turn it is carries on shape and side as well as tint: the two bubbles differ
        // by alignment and by border, so they stay apart where the tint does not survive.
        className={`max-w-[85%] rounded-lg px-3 py-2 text-xs leading-relaxed wrap-break-word ${
          operator
            ? "rounded-br-sm bg-primary-soft text-ink"
            : message.incomplete && !message.stopped
              ? "rounded-bl-sm border border-critical/50 bg-panel-strong text-ink-secondary"
              : "rounded-bl-sm border border-border bg-panel-strong text-ink-secondary"
        }`}
      >
            {/* The operator's own words stay literal — they typed them, so reinterpreting `*` as emphasis
                would be this panel putting words in their mouth. */}
        {operator ? message.text : <MessageBody text={message.text} streaming={streaming} />}
            {/* Never shown as a whole reply — the module's own `incomplete` flag, carried straight through. */}
        {!operator && message.incomplete && (
          message.stopped ? (
              // Not critical-coloured and not called a break: nothing went wrong here, the operator
              // ended it.
            <div className="mt-1 text-[10px] font-semibold text-ink-faint">■ stopped by you</div>
          ) : (
            <div className="mt-1 text-[10px] font-semibold text-critical">⚠ incomplete — broke off</div>
          )
        )}
      </div>
    </div>
  );
}

function Composer({
  onSend,
  onStop,
  disabled,
  children,
}: {
  onSend: (text: string) => void;
  /** Ends the turn in flight. Takes the place of Send while one is running — the button the operator is
   *  looking at is the one they can use, and there is nothing else in this corner to reach for. */
  onStop: () => void;
  disabled: boolean;
  /** Rendered between the box and the send row — the model picker, today. */
  children?: ReactNode;
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
      {children}
      <div className="mt-2 flex items-center gap-2">
        <span className="text-[10px] text-ink-faint">Enter sends · Shift+Enter new line</span>
        {disabled ? (
          <button
            type="button"
            onClick={onStop}
            className="ml-auto cursor-pointer rounded border border-critical/40 px-2 py-1 text-xs text-critical transition-colors hover:bg-critical hover:text-ink-inverse"
          >
            Stop
          </button>
        ) : (
          <button
            type="button"
            onClick={submit}
            disabled={draft.trim() === ""}
            className="ml-auto cursor-pointer rounded border border-primary-line bg-primary-soft px-2 py-1 text-xs text-ink transition-colors hover:bg-primary-strong hover:text-ink-inverse disabled:cursor-not-allowed disabled:border-border disabled:bg-transparent disabled:text-ink-faint"
          >
            Send
          </button>
        )}
      </div>
    </div>
  );
}
