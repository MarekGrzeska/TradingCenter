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
      <div className="flex w-11 shrink-0 flex-col items-center border-l border-border bg-panel py-2">
        <button
          type="button"
          onClick={() => store.setExpanded(true)}
          aria-label="Open agent chat"
          aria-expanded={false}
          aria-controls="agent-chat-panel"
          title="Agent chat"
          className="flex flex-col items-center gap-2 rounded px-1 py-2 text-ink-muted transition-colors hover:bg-panel-strong hover:text-ink"
        >
          <span aria-hidden className="text-base leading-none">
            ✦
          </span>
          {/* Vertical, so the rail can stay narrow enough to cost the charts nothing. */}
          <span aria-hidden className="text-[11px] tracking-wide [writing-mode:vertical-rl]">
            Agent
          </span>
        </button>
      </div>
    );
  }

  return (
    <aside
      id="agent-chat-panel"
      aria-label="Agent chat"
      className="flex w-96 shrink-0 flex-col border-l border-border bg-panel"
    >
      <header className="flex h-12 shrink-0 items-center gap-2 border-b border-border px-3">
        <span aria-hidden className="text-ink-muted">
          ✦
        </span>
        <span className="text-sm font-semibold">Agent</span>
        <span className="rounded border border-border px-1.5 py-0.5 text-[10px] text-ink-muted">
          mockup
        </span>
        <button
          type="button"
          onClick={() => store.setExpanded(false)}
          aria-label="Collapse agent chat"
          aria-expanded
          aria-controls="agent-chat-panel"
          className="ml-auto rounded px-2 py-1 text-sm text-ink-muted transition-colors hover:bg-panel-strong hover:text-ink"
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
        className={`max-w-[85%] rounded-lg px-3 py-2 text-xs leading-relaxed wrap-break-word ${
          operator
            ? "bg-accent/20 text-ink"
            : "border border-border bg-panel-strong text-ink-secondary"
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
    <div className="shrink-0 border-t border-border p-3">
      <textarea
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={onKeyDown}
        rows={2}
        aria-label="Message the agent"
        placeholder="Ask the agent…"
        className="w-full resize-none rounded border border-border bg-canvas px-2 py-1.5 text-xs text-ink placeholder:text-ink-muted focus:border-accent focus:outline-none"
      />
      <div className="mt-2 flex items-center gap-2">
        <span className="text-[10px] text-ink-muted">Enter sends · Shift+Enter new line</span>
        <button
          type="button"
          onClick={submit}
          disabled={draft.trim() === ""}
          className="ml-auto rounded border border-border px-2 py-1 text-xs text-ink transition-colors hover:bg-panel-strong disabled:cursor-not-allowed disabled:text-ink-muted disabled:hover:bg-transparent"
        >
          Send
        </button>
      </div>
    </div>
  );
}
