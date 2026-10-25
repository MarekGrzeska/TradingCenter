import { Fragment, useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import type { AgentToolCall } from "./agentApi";
import type { AgentChatState, ChatMessage } from "./agentChatStore";
import { MessageBody } from "./MessageBody";
import { ToolCallEntry } from "./ToolCallEntry";

/**
 * The parts of a conversation on screen, shared by the terminal's agent panel and the chat beside a strategy's editor
 * (`terminal-strategies`): what a turn shows is one thing however many places ask it.
 */

/**
 * Built entirely from `state.models` — the terminal must not carry a list of its own. A catalogue that
 * failed to load says so in words rather than falling back to anything baked in here.
 */
export function ModelPicker({
  state,
  onChange,
}: {
  state: AgentChatState;
  onChange: (modelId: string) => void;
}) {
  // Two conversations can be on screen at once — the panel and a strategy's — and an id must name one picker.
  const pickerId = useId();
  if (state.modelsStatus === "unreachable") {
    return (
      <p className="mt-2 text-xs text-critical">
        model picker unavailable — the catalogue could not be read
      </p>
    );
  }

  return (
    <div className="mt-2 flex items-center gap-2">
      <label htmlFor={pickerId} className="text-[11px] text-ink-muted">
        Model
      </label>
      <select
        id={pickerId}
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

export function Transcript({
  messages,
  turn,
  unclaimedToolCalls,
  emptyText = "Ask the agent about the market on screen.",
}: {
  messages: readonly ChatMessage[];
  turn: AgentChatState["turn"];
  unclaimedToolCalls: readonly AgentToolCall[];
  emptyText?: string;
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
        <p className="text-xs text-ink-faint">{emptyText}</p>
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

export function Composer({
  onSend,
  onStop,
  disabled,
  placeholder = "Ask the agent…",
  children,
}: {
  onSend: (text: string) => void;
  /** Ends the turn in flight. Takes the place of Send while one is running — the button the operator is
   *  looking at is the one they can use, and there is nothing else in this corner to reach for. */
  onStop: () => void;
  disabled: boolean;
  placeholder?: string;
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
        placeholder={disabled ? "Waiting for the reply…" : placeholder}
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
