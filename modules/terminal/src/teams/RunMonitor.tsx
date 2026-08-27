import { useMemo, useState } from "react";
import { Button } from "../ui/Button";
import { UnreachableNotice } from "../ui/UnreachableNotice";
import { MessageBody } from "../agent/MessageBody";
import { useRead } from "../data/query";
import { formatInstant } from "../ui/formatTime";
import { RunOutputsDialog } from "./RunOutputsDialog";
import { TeamCanvas } from "./TeamCanvas";
import { outcomeOf, stopCause, type TeamRun, type TeamRunStep, type TeamRunToolCall, type TeamTrade } from "./runs";
import type { TeamDefinition, TeamLayout, TeamsApi, TeamsModel } from "./teamsApi";
import { useRunMonitor } from "./useRunMonitor";

/** Before the revision has been read, and after a read that failed: no graph, and the
 *  version unknown. */
const NO_GRAPH: { definition: TeamDefinition | null; version: number | null; places: TeamLayout } =
  { definition: null, version: null, places: new Map() };

/**
 * A run watched on the picture of the team, because a run takes minutes and a still picture does not separate
 * work from a hang. The graph is the run's **revision**, never the team's latest (specs/teams-runs).
 */
export function RunMonitor({
  api,
  runId,
  models,
  onClose,
}: {
  api: TeamsApi;
  runId: number;
  models: TeamsModel[];
  /** Absent inside `TeamRunsView`, which has a header and a way back of its own — two
   *  "← Catalogue" buttons one above the other are one too many. */
  onClose?(): void;
}) {
  const monitor = useRunMonitor(api, runId);
  const { run, steps, toolCalls, trades } = monitor;
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  // Reading what the agents wrote is a different job from watching whether they are working, and the 20rem
  // column beside the canvas is shaped for the second one (`RunOutputsDialog`).
  const [readingOutputs, setReadingOutputs] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [stopError, setStopError] = useState<string | null>(null);

  const revisionId = run?.teamRevisionId ?? null;
  // The revision and the team's arrangement, so a run is watched on the picture the operator built. A layout
  // that cannot be read is not worth failing over; `onFailure: "forget"` because a stale graph is not this run.
  const graph = useRead({
    key: ["teams", "revision", revisionId],
    read: async (signal) => {
      const revision = await api.revisionById(revisionId!, signal);
      const places = await api.layout(revision.teamId, signal).catch(() => new Map<string, { x: number; y: number }>());
      return { definition: revision.definition, version: revision.version, places };
    },
    initial: NO_GRAPH,
    fallbackMessage: "the team's revision could not be read",
    enabled: revisionId !== null,
    onFailure: "forget",
  });
  const { definition, version, places } = graph.value;

  const runStatuses = useMemo(
    () => new Map(steps.map((step) => [step.agentKey, step.status])),
    [steps],
  );
  const callsByAgent = useMemo(() => {
    const grouped = new Map<string, TeamRunToolCall[]>();
    for (const call of toolCalls) {
      grouped.set(call.agentKey, [...(grouped.get(call.agentKey) ?? []), call]);
    }
    return grouped;
  }, [toolCalls]);

  const tradesByAgent = useMemo(() => {
    const grouped = new Map<string, TeamTrade[]>();
    for (const trade of trades) {
      grouped.set(trade.agentKey, [...(grouped.get(trade.agentKey) ?? []), trade]);
    }
    return grouped;
  }, [trades]);

  const selectedStep = steps.find((step) => step.agentKey === selectedKey) ?? null;
  const working = run !== null && (run.status === "pending" || run.status === "running");

  async function stop() {
    if (run === null) return;
    setStopping(true);
    setStopError(null);
    try {
      await api.cancelRun(run.id, new AbortController().signal);
    } catch (cause) {
      setStopError(cause instanceof Error ? cause.message : "the run could not be stopped");
    } finally {
      setStopping(false);
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex flex-wrap items-center gap-2 border-b border-border p-2">
        {onClose && (
          <Button onClick={onClose}>
            ← Catalogue
          </Button>
        )}
        <span className="text-sm text-ink">
          Run {runId}
          {version !== null && <span className="text-xs text-ink-faint"> · revision {version}</span>}
        </span>
        {run && <RunBadge status={run.status} />}
        {/* Enabled while the run still works, deliberately: what has already been written
            is worth reading before the rest arrives, and the dialog renders whatever the
            stream has delivered so far. The count is on the button because it is the
            question the button answers — is there anything in there yet. */}
        <Button
          onClick={() => setReadingOutputs(true)}
          disabled={steps.length === 0}
        >
          Outputs ({steps.filter((step) => step.output).length})
        </Button>
        {working && (
          <Button
            tone="critical"
            onClick={stop}
            disabled={stopping}
          >
            {stopping ? "Stopping…" : "Stop"}
          </Button>
        )}
        {run?.startedAt !== null && run?.startedAt !== undefined && (
          <span className="text-xs text-ink-faint">started {formatInstant(run.startedAt)}</span>
        )}
      </header>

      {/* The module's own sentence, whatever stopped it, headed by which ceiling it was: one operator buys
          more budget, another learns their team wanted to trade more than they allowed (specs/terminal-teams). */}
      {run?.stoppedReason && (
        <p className="border-b border-border px-2 py-1 text-xs text-warning">
          <StopHeading cause={stopCause(run.stoppedReason)} />
          {run.stoppedReason}
        </p>
      )}
      {stopError && (
        <p className="border-b border-border px-2 py-1 text-xs text-critical">{stopError}</p>
      )}
      {monitor.status === "error" && (
        <UnreachableNotice
          className="border-b border-border px-2 py-1 text-xs text-critical"
          onRetry={monitor.reload}
          retryLabel="Watch again"
        >
          {monitor.error}
        </UnreachableNotice>
      )}

      <div className="grid min-h-0 flex-1 grid-cols-[1fr_20rem]">
        {definition ? (
          <TeamCanvas
            definition={definition}
            models={models}
            selectedKey={selectedKey}
            refusal={null}
            runStatuses={runStatuses}
            places={places}
            onSelect={setSelectedKey}
          />
        ) : (
          <p className="p-4 text-sm text-ink-muted">
            {monitor.status === "loading"
              ? "Opening the run…"
              : "The revision this run works on could not be read."}
          </p>
        )}

        <div className="flex h-full min-h-0 flex-col gap-3 overflow-auto border-l border-border p-3">
          {selectedStep ? (
            <AgentWork
              step={selectedStep}
              role={definition?.agents.find((agent) => agent.key === selectedKey)?.role ?? null}
              calls={callsByAgent.get(selectedStep.agentKey) ?? []}
              trades={tradesByAgent.get(selectedStep.agentKey) ?? []}
              runOver={run !== null && !working}
            />
          ) : (
            <RunSummary
              run={run}
              steps={steps}
              calls={toolCalls}
              trades={trades}
              runOver={run !== null && !working}
            />
          )}
        </div>
      </div>

      {readingOutputs && (
        <RunOutputsDialog
          runId={runId}
          steps={steps}
          roleOf={(agentKey) =>
            definition?.agents.find((agent) => agent.key === agentKey)?.role ?? null
          }
          callsByAgent={callsByAgent}
          tradesByAgent={tradesByAgent}
          runOver={run !== null && !working}
          onClose={() => setReadingOutputs(false)}
        />
      )}
    </div>
  );
}

/** What one agent has produced, and what it reached for on the way. This is the other
 *  half of the requirement — the picture says who is working, this says what came of it
 *  ("MUST udostępniać to, co agenci wypracowali, oraz wywołane przez nich narzędzia"). */
function AgentWork({
  step,
  role,
  calls,
  trades,
  runOver,
}: {
  step: TeamRunStep;
  role: string | null;
  calls: TeamRunToolCall[];
  trades: TeamTrade[];
  runOver: boolean;
}) {
  return (
    <>
      <div>
        <h3 className="text-sm text-ink">{role ?? step.agentKey}</h3>
        <p className="text-xs text-ink-faint">
          {step.status} · {step.rounds} round{step.rounds === 1 ? "" : "s"}
          {step.finishedAt !== null && ` · finished ${formatInstant(step.finishedAt)}`}
        </p>
      </div>

      {/* No `min-h-0` here, and that is the fix for a real overlap: with it, this section
          was allowed to shrink below its own content while the rendered output kept its
          height, so a long analyst report drew straight through the "Tools called" list
          underneath it. The column scrolls; the sections inside it keep their height. */}
      <section className="flex flex-col gap-1">
        <h4 className="text-xs uppercase tracking-wide text-ink-faint">Output</h4>
        {step.output ? (
          // The same renderer the chat uses, for the same reason: this is model prose, and as raw text it
          // reads as `**` and `-`. The full-width version is `RunOutputsDialog`.
          <div className="text-xs text-ink">
            <MessageBody text={step.output} />
          </div>
        ) : (
          <p className="text-xs text-ink-muted">
            {step.status === "pending" ? "waiting for its predecessors" : "nothing yet"}
          </p>
        )}
      </section>

      {/* Above the tool calls, not folded into them: a call is what the agent asked for, an order is what
          happened to the account, and the operator watching a team trade is asking the second. */}
      {trades.length > 0 && (
        <section className="flex flex-col gap-1">
          <h4 className="text-xs uppercase tracking-wide text-ink-faint">Orders</h4>
          {trades.map((trade) => (
            <TradeRow key={trade.id} trade={trade} runOver={runOver} />
          ))}
        </section>
      )}

      <section className="flex flex-col gap-1">
        <h4 className="text-xs uppercase tracking-wide text-ink-faint">Tools called</h4>
        {calls.length === 0 ? (
          <p className="text-xs text-ink-muted">none</p>
        ) : (
          calls.map((call) => (
            <div
              key={`${call.roundIndex}-${call.position}-${call.toolName}`}
              className="flex items-baseline justify-between gap-2 text-xs"
            >
              <span className="text-ink">{call.toolName}</span>
              <span className={call.outcome === "ok" ? "text-ink-faint" : "text-warning"}>
                {call.outcome} · {call.durationMs} ms
              </span>
            </div>
          ))
        )}
      </section>
    </>
  );
}

function RunSummary({
  run,
  steps,
  calls,
  trades,
  runOver,
}: {
  run: TeamRun | null;
  steps: TeamRunStep[];
  calls: TeamRunToolCall[];
  trades: TeamTrade[];
  runOver: boolean;
}) {
  if (run === null) return <p className="text-xs text-ink-muted">Reading the run…</p>;
  const done = steps.filter((step) => step.status === "completed").length;
  return (
    <>
      <p className="text-xs text-ink-muted">
        Pick an agent to read what it produced and what it called.
      </p>
      <dl className="flex flex-col gap-1 text-xs text-ink">
        <Row label="Status" value={run.status} />
        <Row label="Agents finished" value={`${done} of ${steps.length}`} />
        <Row label="Tool calls" value={String(calls.length)} />
        {run.finishedAt !== null && <Row label="Finished" value={formatInstant(run.finishedAt)} />}
      </dl>

      {/* The whole run's orders, in the order they were placed. This is what a run stopped
          by its order limit is read on — the ceiling says how many, and this says which
          (specs/terminal-teams, "pokazuje złożone dotąd zlecenia"). */}
      {trades.length > 0 && (
        <section className="flex flex-col gap-1">
          <h4 className="text-xs uppercase tracking-wide text-ink-faint">
            Orders placed ({trades.length})
          </h4>
          {trades.map((trade) => (
            <TradeRow key={trade.id} trade={trade} runOver={runOver} />
          ))}
        </section>
      )}
    </>
  );
}

/** One order: what, which way, how much, and what came of it. The size and the level are
 *  shown as the module wrote them — strings, never rescaled here. */
function TradeRow({ trade, runOver }: { trade: TeamTrade; runOver: boolean }) {
  const outcome = outcomeOf(trade, runOver);
  return (
    <div className="flex items-baseline justify-between gap-2 text-xs">
      <span className="text-ink">
        {trade.symbol ?? trade.toolName}
        {trade.direction && <span className="text-ink-faint"> {trade.direction}</span>}
        {trade.size && <span className="text-ink-faint"> ×{trade.size}</span>}
        {trade.level && <span className="text-ink-faint"> @{trade.level}</span>}
      </span>
      <span className={outcome.known ? "text-ink-faint" : "text-warning"}>{outcome.text}</span>
    </div>
  );
}

/** Which ceiling this was, when the sentence says. Absent for anything else — a timeout,
 *  the operator's own interruption, an agent that failed — where the module's sentence is
 *  already the whole of what there is to say. */
function StopHeading({ cause }: { cause: ReturnType<typeof stopCause> }) {
  if (cause !== "orders" && cause !== "cost") return null;
  return (
    <span className="mr-2 font-medium uppercase">
      {cause === "orders" ? "Order limit" : "Cost limit"}
    </span>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <dt className="text-ink-faint">{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

const RUN_TONE: Record<string, string> = {
  pending: "text-ink-muted",
  running: "text-primary",
  completed: "text-good",
  failed: "text-critical",
  cancelled: "text-warning",
};

function RunBadge({ status }: { status: string }) {
  return (
    <span className={`text-xs ${RUN_TONE[status] ?? "text-ink-muted"}`} data-testid="run-status">
      {status}
    </span>
  );
}
