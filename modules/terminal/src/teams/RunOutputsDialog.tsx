import { useState } from "react";
import { MessageBody } from "../agent/MessageBody";
import { ModalShell } from "../ui/ModalShell";
import { formatInstant } from "../ui/formatTime";
import { outcomeOf, type TeamRunStep, type TeamRunToolCall, type TeamTrade } from "./runs";

/**
 * What the agents wrote, in a window wide enough to read it in.
 *
 * The monitor's right-hand column is 20rem and shows one agent at a time, which is the
 * right shape for the question a run in flight asks — who is working, is anything stuck.
 * It is the wrong shape for the question a *finished* run asks, which is "what did they
 * say", and the answer is prose: several paragraphs per agent, written by a model that had
 * no idea it was going into a column that narrow. The canvas stays where it is; this is a
 * second door to the same rows.
 *
 * `All agents` is the default and it exists because reading a finished run is reading it in
 * order — one agent handed to the next, and the seams between them are half of what there
 * is to learn. Picking one agent narrows to it, with what it called and what it placed
 * underneath, because those explain an output that otherwise looks like an assertion.
 *
 * Nothing here refetches: it renders what `useRunMonitor` already holds, so opening this
 * while a run is still working shows exactly as much as the stream has delivered, and it
 * keeps arriving with the dialog open.
 */
export function RunOutputsDialog({
  runId,
  steps,
  roleOf,
  callsByAgent,
  tradesByAgent,
  runOver,
  onClose,
}: {
  runId: number;
  steps: TeamRunStep[];
  /** The role from the run's own revision, or `null` when that revision could not be
   *  read — then the agent's key is the only name there is, and it is used. */
  roleOf(agentKey: string): string | null;
  callsByAgent: Map<string, TeamRunToolCall[]>;
  tradesByAgent: Map<string, TeamTrade[]>;
  runOver: boolean;
  onClose(): void;
}) {
  const [showing, setShowing] = useState<string | null>(null);
  const selected = steps.find((step) => step.agentKey === showing) ?? null;
  const named = (step: TeamRunStep) => roleOf(step.agentKey) ?? step.agentKey;

  return (
    <ModalShell
      title={`Run ${runId} — what the agents wrote`}
      // `reading`, not `wide`: this is the one window whose whole job is several pages of
      // prose, so it takes the screen rather than a comfortable dialog's worth of it.
      size="reading"
      showCloseButton
      onClose={onClose}
      footer={
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-ink-faint">
            {steps.filter((step) => step.output).length} of {steps.length} have written
            something
          </span>
          <button
            type="button"
            onClick={onClose}
            className="cursor-pointer rounded border border-primary bg-primary-soft px-3 py-1 text-xs text-ink hover:bg-primary-strong hover:text-ink-inverse"
          >
            Done
          </button>
        </div>
      }
    >
      <div className="grid min-h-0 flex-1 gap-4 md:grid-cols-[16rem_1fr]">
        <nav className="flex min-h-0 flex-col gap-1 overflow-auto md:border-r md:border-border md:pr-4">
          <PickerButton
            label="All agents"
            hint={`${steps.length} in this run`}
            active={showing === null}
            onClick={() => setShowing(null)}
          />
          {steps.map((step) => (
            <PickerButton
              key={step.agentKey}
              label={named(step)}
              hint={`${step.status}${step.output ? "" : " · nothing yet"}`}
              active={showing === step.agentKey}
              onClick={() => setShowing(step.agentKey)}
            />
          ))}
        </nav>

        <div className="flex min-h-0 flex-col gap-4 overflow-auto">
          {selected === null ? (
            steps.length === 0 ? (
              <p className="text-sm text-ink-muted">This run has no steps to read yet.</p>
            ) : (
              steps.map((step) => (
                <OneOutput key={step.agentKey} step={step} role={named(step)} />
              ))
            )
          ) : (
            <>
              <OneOutput step={selected} role={named(selected)} />
              <Called calls={callsByAgent.get(selected.agentKey) ?? []} />
              <Placed
                trades={tradesByAgent.get(selected.agentKey) ?? []}
                runOver={runOver}
              />
            </>
          )}
        </div>
      </div>
    </ModalShell>
  );
}

function PickerButton({
  label,
  hint,
  active,
  onClick,
}: {
  label: string;
  hint: string;
  active: boolean;
  onClick(): void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`cursor-pointer rounded border px-2 py-1 text-left text-xs ${
        active
          ? "border-primary-line bg-primary-soft text-ink"
          : "border-transparent text-ink hover:border-border hover:bg-panel-strong"
      }`}
    >
      <span className="block font-medium">{label}</span>
      <span className="block text-ink-faint">{hint}</span>
    </button>
  );
}

/** One agent's output, as the Markdown the model actually wrote.
 *
 *  Through `MessageBody`, the same renderer the chat uses, rather than a second one: an
 *  agent's output is model prose in both places, full of `**` and `-` lists that read as
 *  punctuation noise until something interprets them. Reusing it also inherits the reason
 *  it is safe — no `rehype-raw`, so raw HTML in an output is never rendered at all.
 *
 *  Capped at `max-w-4xl` rather than filling the window: a line of text 90rem wide is as
 *  hard to read as one 20rem wide, for the opposite reason. Wider than `max-w-prose`
 *  because the window is now the screen and the extra width is there to be used. */
function OneOutput({ step, role }: { step: TeamRunStep; role: string }) {
  return (
    <section className="flex flex-col gap-1">
      <h3 className="flex items-baseline gap-2 text-sm text-ink">
        {role}
        <span className="text-xs text-ink-faint">
          {step.status} · {step.rounds} round{step.rounds === 1 ? "" : "s"}
          {step.finishedAt !== null && ` · finished ${formatInstant(step.finishedAt)}`}
        </span>
      </h3>
      {step.output ? (
        <div className="max-w-4xl text-sm leading-relaxed text-ink">
          <MessageBody text={step.output} />
        </div>
      ) : (
        <p className="text-xs text-ink-muted">
          {step.status === "pending" ? "waiting for its predecessors" : "nothing yet"}
        </p>
      )}
    </section>
  );
}

function Called({ calls }: { calls: TeamRunToolCall[] }) {
  return (
    <section className="flex flex-col gap-1">
      <h4 className="text-xs uppercase tracking-wide text-ink-faint">Tools called</h4>
      {calls.length === 0 ? (
        <p className="text-xs text-ink-muted">none</p>
      ) : (
        calls.map((call) => (
          <div
            key={`${call.roundIndex}-${call.position}-${call.toolName}`}
            className="flex max-w-4xl items-baseline justify-between gap-2 text-xs"
          >
            <span className="text-ink">{call.toolName}</span>
            <span className={call.outcome === "ok" ? "text-ink-faint" : "text-warning"}>
              {call.outcome} · {call.durationMs} ms
            </span>
          </div>
        ))
      )}
    </section>
  );
}

/** Only when there are any — most agents never place an order, and a permanent empty
 *  "Orders" heading would make the ones that do look ordinary. */
function Placed({ trades, runOver }: { trades: TeamTrade[]; runOver: boolean }) {
  if (trades.length === 0) return null;
  return (
    <section className="flex flex-col gap-1">
      <h4 className="text-xs uppercase tracking-wide text-ink-faint">Orders</h4>
      {trades.map((trade) => {
        const outcome = outcomeOf(trade, runOver);
        return (
          <div
            key={trade.id}
            className="flex max-w-4xl items-baseline justify-between gap-2 text-xs"
          >
            <span className="text-ink">
              {trade.symbol ?? trade.toolName}
              {trade.direction && <span className="text-ink-faint"> {trade.direction}</span>}
              {trade.size && <span className="text-ink-faint"> ×{trade.size}</span>}
              {trade.level && <span className="text-ink-faint"> @{trade.level}</span>}
            </span>
            <span className={outcome.known ? "text-ink-faint" : "text-warning"}>
              {outcome.text}
            </span>
          </div>
        );
      })}
    </section>
  );
}
