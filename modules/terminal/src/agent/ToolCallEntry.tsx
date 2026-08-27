import { useState } from "react";

import type { AgentToolCall, ToolOutcome } from "./agentApi";

/**
 * One tool call in the transcript where it happened: it is part of how the reply was reached, and a drawer
 * elsewhere is a place nobody looks. Collapsed and expanded one at a time — eight open results bury the turn.
 */

const OUTCOME_LABEL: Record<ToolOutcome, string> = {
  ok: "ok",
  refused: "refused",
  unavailable: "no answer",
  unknown: "outcome unknown",
  unrecognised: "unrecognised",
};

/**
 * The four the module distinguishes never collapse into fewer: a refusal is the archive answering "not like that",
 * unreachable means nothing was asked. `unknown` is loudest — a call that could have changed the account.
 */
const OUTCOME_STYLE: Record<ToolOutcome, string> = {
  ok: "text-ink-muted",
  refused: "text-warning",
  unavailable: "text-critical",
  unknown: "text-critical",
  unrecognised: "text-ink-muted",
};

export function ToolCallEntry({ call }: { call: AgentToolCall }) {
  const [expanded, setExpanded] = useState(false);
  const summary = `${call.name} — ${OUTCOME_LABEL[call.outcome]}`;

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] min-w-0 rounded border border-border bg-panel/60 text-[11px]">
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          aria-expanded={expanded}
          aria-label={expanded ? `Collapse ${summary}` : `Expand ${summary}`}
          className="flex w-full cursor-pointer items-center gap-1.5 px-2 py-1 text-left hover:bg-panel-strong"
        >
          {/* A caret, not a word: the row is already three pieces of text wide, and the
              button's own aria-label carries what this means to a screen reader. */}
          <span aria-hidden className="text-ink-faint">
            {expanded ? "▾" : "▸"}
          </span>
          <span className="truncate font-mono text-ink-secondary">{call.name}</span>
          {call.source === "module" && (
            // Server calls are the common case and say nothing extra; the one tool this module runs
            // itself is the exception worth naming.
            <span
              title="Run by this module, not the tool server"
              className="shrink-0 rounded border border-primary-line px-1 text-[10px] tracking-wide text-primary uppercase"
            >
              module
            </span>
          )}
          <span className={`ml-auto shrink-0 font-semibold ${OUTCOME_STYLE[call.outcome]}`}>
            {OUTCOME_LABEL[call.outcome]}
          </span>
          <span className="shrink-0 text-ink-faint">{call.durationMs} ms</span>
        </button>
        {expanded && (
          <div className="border-t border-border px-2 py-1.5">
            <ToolCallDetail label="arguments" body={JSON.stringify(call.arguments)} />
            <ToolCallDetail
              label={call.outcome === "ok" ? "result" : "reason"}
              body={call.resultText}
            />
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * `<pre>` and `wrap-break-word` together: a tool's answer is JSON often enough that collapsed whitespace is
 * unreadable, and long enough to push the conversation off-screen. Text — this is a string, never markup.
 */
function ToolCallDetail({ label, body }: { label: string; body: string }) {
  return (
    <div className="mt-1 first:mt-0">
      <div className="text-[10px] tracking-wide text-ink-faint uppercase">{label}</div>
      <pre className="max-h-48 overflow-auto font-mono text-[11px] whitespace-pre-wrap text-ink-secondary wrap-break-word">
        {body}
      </pre>
    </div>
  );
}
