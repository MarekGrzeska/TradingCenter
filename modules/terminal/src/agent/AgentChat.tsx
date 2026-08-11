import { useEffect, useRef, useState, useSyncExternalStore, type KeyboardEvent } from "react";

import { agentChatStore, type AgentChatStore, type ChatMessage } from "./agentChatStore";

/**
 * Mounted once in `Shell`, as a sibling of the router outlet rather than inside it: the
 * panel belongs to the terminal, not to a tab, so switching tabs neither hides it nor
 * remounts the conversation.
 *
 * Collapsed it is a rail on the right edge — a place, not a floating button, so the way in
 * is always in the same pixels whatever tab is on screen. Expanded it is a column in the
 * shell's flex row, which is what pushes the tab content aside instead of covering it; the
 * chart's ResizeObserver picks the new width up on its own.
 */
export function AgentChat({ store = agentChatStore }: { store?: AgentChatStore } = {}) {
  const state = useSyncExternalStore(store.subscribe, store.getSnapshot);

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
        className="group flex w-9 shrink-0 cursor-pointer flex-col items-center justify-center border-l border-accent/40 bg-agent-surface transition-colors hover:bg-agent-surface-strong"
      >
        <span
          aria-hidden
          className="flex flex-col items-center gap-1.5 rounded-l-md border border-r-0 border-accent/40 bg-accent/15 px-1.5 py-3 text-accent transition-colors group-hover:bg-accent/25"
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
      className="flex w-96 shrink-0 flex-col border-l border-accent/40 bg-agent-surface"
    >
      <header className="flex h-12 shrink-0 items-center gap-2 border-b border-accent/25 bg-agent-surface-strong px-3">
        <AgentGlyph className="h-4 w-4 text-accent" />
        <span className="text-sm font-semibold">Agent</span>
        <span className="rounded border border-accent/40 px-1.5 py-0.5 text-[10px] text-accent">
          mockup
        </span>
        <button
          type="button"
          onClick={() => store.setExpanded(false)}
          aria-label="Collapse agent chat"
          aria-expanded
          aria-controls="agent-chat-panel"
          className="ml-auto cursor-pointer rounded p-1.5 text-ink-muted transition-colors hover:bg-accent/20 hover:text-ink"
        >
          <Chevron className="h-4 w-4" direction="right" />
        </button>
      </header>

      <Transcript messages={state.messages} />
      <Composer onSend={(text) => store.send(text)} />
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

function Transcript({ messages }: { messages: readonly ChatMessage[] }) {
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // `scrollTop`, not `scrollIntoView`: the latter is not implemented in jsdom, and the
    // container is the thing that scrolls anyway.
    const list = listRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [messages.length]);

  return (
    <div
      ref={listRef}
      // `polite`: a reply arriving is worth announcing, never worth cutting off whatever
      // the operator is reading on the chart beside it.
      aria-live="polite"
      className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-3"
    >
      {messages.map((message) => (
        <Bubble key={message.id} message={message} />
      ))}
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
            ? "rounded-br-sm bg-accent/20 text-ink"
            : "rounded-bl-sm border border-accent/20 bg-agent-surface-strong text-ink-secondary"
        }`}
      >
        {message.text}
      </div>
    </div>
  );
}

function Composer({ onSend }: { onSend: (text: string) => void }) {
  const [draft, setDraft] = useState("");

  function submit(): void {
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
    <div className="shrink-0 border-t border-accent/25 bg-agent-surface-strong p-3">
      <textarea
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={onKeyDown}
        rows={2}
        aria-label="Message the agent"
        placeholder="Ask the agent…"
        className="w-full resize-none rounded border border-accent/30 bg-canvas px-2 py-1.5 text-xs text-ink placeholder:text-ink-muted focus:border-accent focus:outline-none"
      />
      <div className="mt-2 flex items-center gap-2">
        <span className="text-[10px] text-ink-muted">Enter sends · Shift+Enter new line</span>
        <button
          type="button"
          onClick={submit}
          disabled={draft.trim() === ""}
          className="ml-auto cursor-pointer rounded border border-accent/40 bg-accent/15 px-2 py-1 text-xs text-ink transition-colors hover:bg-accent/30 disabled:cursor-not-allowed disabled:border-border disabled:bg-transparent disabled:text-ink-muted"
        >
          Send
        </button>
      </div>
    </div>
  );
}
