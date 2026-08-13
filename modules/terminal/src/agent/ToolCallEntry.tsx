import { useState } from "react";

import type { AgentToolCall, ToolOutcome } from "./agentApi";

/**
 * One tool call, in the transcript where it happened rather than in a panel beside it.
 * It is part of how the reply was reached, and a diagnostic drawer somewhere else is a
 * place nobody looks until they already suspect something (`terminal-agent-chat` spec,
 * "Wywołanie MUST stać w transkrypcie tam, gdzie padło").
 *
 * Collapsed by default and expanded one at a time: a turn is allowed eight calls, and
 * eight open results would bury the rozmowa they were made for.
 */

const OUTCOME_LABEL: Record<ToolOutcome, string> = {
  ok: "ok",
  refused: "refused",
  unavailable: "no answer",
  unknown: "unknown",
};

/**
 * The three the module distinguishes never collapse into two, and the colours carry that:
 * a refusal is the archive answering "not like that" — worth noticing, not an alarm — while
 * an unreachable server means nothing was asked and nothing is known either way. Reading
 * the second as the first is how "the archive has no data" gets said about data the
 * archive has.
 */
const OUTCOME_STYLE: Record<ToolOutcome, string> = {
  ok: "text-ink-muted",
  refused: "text-warning",
  unavailable: "text-critical",
  unknown: "text-ink-muted",
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
 * `<pre>` and `wrap-break-word` together: a tool's answer is JSON often enough that
 * collapsing its whitespace would make it unreadable, and long enough that letting it set
 * the panel's width would push the rozmowa off-screen. Rendered as text — this is a
 * string from the archive and never markup, the same rule the agent's own reply follows
 * in `MessageBody`.
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
