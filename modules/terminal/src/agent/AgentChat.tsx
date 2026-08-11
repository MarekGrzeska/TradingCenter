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
        className="group flex w-9 shrink-0 cursor-pointer flex-col items-center justify-center border-l border-agent-edge/40 bg-agent-surface transition-colors hover:bg-agent-surface-strong"
      >
        <span
          aria-hidden
          className="flex flex-col items-center gap-1.5 rounded-l-md border border-r-0 border-agent-edge/40 bg-agent-edge/15 px-1.5 py-3 text-agent-edge transition-colors group-hover:bg-agent-edge/25"
        >
          <span className="text-sm leading-none">✦</span>
          <span className="text-xs leading-none">‹</span>
        </span>
      </button>
    );
  }

  return (
    <aside
      id="agent-chat-panel"
      aria-label="Agent chat"
      className="flex w-96 shrink-0 flex-col border-l border-agent-edge/40 bg-agent-surface"
    >
      <header className="flex h-12 shrink-0 items-center gap-2 border-b border-agent-edge/25 bg-agent-surface-strong px-3">
        <span aria-hidden className="text-agent-edge">
          ✦
        </span>
        <span className="text-sm font-semibold">Agent</span>
        <span className="rounded border border-agent-edge/40 px-1.5 py-0.5 text-[10px] text-agent-edge">
          mockup
        </span>
        <button
          type="button"
          onClick={() => store.setExpanded(false)}
          aria-label="Collapse agent chat"
          aria-expanded
          aria-controls="agent-chat-panel"
          className="ml-auto cursor-pointer rounded px-2 py-1 text-sm text-ink-muted transition-colors hover:bg-agent-edge/20 hover:text-ink"
        >
          ›
        </button>
      </header>

      <Transcript messages={state.messages} />
      <Composer onSend={(text) => store.send(text)} />
    </aside>
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
            ? "rounded-br-sm bg-agent-edge/20 text-ink"
            : "rounded-bl-sm border border-agent-edge/20 bg-agent-surface-strong text-ink-secondary"
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
    <div className="shrink-0 border-t border-agent-edge/25 bg-agent-surface-strong p-3">
      <textarea
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={onKeyDown}
        rows={2}
        aria-label="Message the agent"
        placeholder="Ask the agent…"
        className="w-full resize-none rounded border border-agent-edge/30 bg-canvas px-2 py-1.5 text-xs text-ink placeholder:text-ink-muted focus:border-agent-edge focus:outline-none"
      />
      <div className="mt-2 flex items-center gap-2">
        <span className="text-[10px] text-ink-muted">Enter sends · Shift+Enter new line</span>
        <button
          type="button"
          onClick={submit}
          disabled={draft.trim() === ""}
          className="ml-auto cursor-pointer rounded border border-agent-edge/40 bg-agent-edge/15 px-2 py-1 text-xs text-ink transition-colors hover:bg-agent-edge/30 disabled:cursor-not-allowed disabled:border-border disabled:bg-transparent disabled:text-ink-muted"
        >
          Send
        </button>
      </div>
    </div>
  );
}
