import { useEffect, useMemo, useState } from "react";
import { formatInstant } from "../ui/formatTime";
import { TeamCanvas } from "./TeamCanvas";
import type { TeamRun, TeamRunStep, TeamRunToolCall } from "./runs";
import type { TeamDefinition, TeamLayout, TeamsApi, TeamsModel } from "./teamsApi";
import { useRunMonitor } from "./useRunMonitor";

/**
 * A run, watched on the picture of the team it is running.
 *
 * The same canvas the operator composed the team on, with each agent carrying the state
 * of its step — waiting, working, done, failed. That is the requirement and it is not a
 * presentational preference: a run takes minutes, and a picture where nothing moves does
 * not distinguish work from a hang, which is the first thing the operator wants to know
 * (`terminal-teams`, "Przebieg widać na obrazie zespołu w trakcie, nie po fakcie").
 *
 * The graph drawn is the run's **revision**, fetched by the id the run names — never the
 * team's latest. An operator who saved a new revision while this run works would
 * otherwise watch it against a team it is not running (specs/teams-runs).
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
  onClose(): void;
}) {
  const monitor = useRunMonitor(api, runId);
  const { run, steps, toolCalls } = monitor;
  const [definition, setDefinition] = useState<TeamDefinition | null>(null);
  const [places, setPlaces] = useState<TeamLayout>(new Map());
  const [version, setVersion] = useState<number | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [stopping, setStopping] = useState(false);
  const [stopError, setStopError] = useState<string | null>(null);

  const revisionId = run?.teamRevisionId ?? null;
  useEffect(() => {
    if (revisionId === null) return;
    let cancelled = false;
    const controller = new AbortController();

    api
      .revisionById(revisionId, controller.signal)
      .then(async (revision) => {
        if (cancelled) return;
        setDefinition(revision.definition);
        setVersion(revision.version);
        // The team's arrangement, so a run is watched on the picture the operator built
        // rather than on a second one laid out from scratch. It belongs to the team and
        // this revision may be older than it — an agent it does not name falls back to
        // `layout()` inside the canvas, which is the case the spec names.
        const layout = await api.layout(revision.teamId, controller.signal).catch(() => new Map());
        if (!cancelled) setPlaces(layout);
      })
      .catch(() => {
        // The stream is still the run's own state and keeps arriving; what is missing is
        // the graph to draw it on, which the body below says outright.
        if (!cancelled) setDefinition(null);
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [api, revisionId]);

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
        <button
          type="button"
          onClick={onClose}
          className="cursor-pointer rounded border border-border px-2 py-1 text-xs text-ink hover:bg-panel-strong"
        >
          ← Catalogue
        </button>
        <span className="text-sm text-ink">
          Run {runId}
          {version !== null && <span className="text-xs text-ink-faint"> · revision {version}</span>}
        </span>
        {run && <RunBadge status={run.status} />}
        {working && (
          <button
            type="button"
            onClick={stop}
            disabled={stopping}
            className="cursor-pointer rounded border border-critical px-2 py-1 text-xs text-critical hover:bg-panel-strong disabled:cursor-not-allowed disabled:opacity-40"
          >
            {stopping ? "Stopping…" : "Stop"}
          </button>
        )}
        {run?.startedAt !== null && run?.startedAt !== undefined && (
          <span className="text-xs text-ink-faint">started {formatInstant(run.startedAt)}</span>
        )}
      </header>

      {/* The module's own sentence, whatever stopped it — a cost ceiling names the cost
          (specs/teams-usage), a timeout names the limit, the operator's own interruption
          says so. Kept above the canvas because it explains everything below it. */}
      {run?.stoppedReason && (
        <p className="border-b border-border px-2 py-1 text-xs text-warning">
          {run.stoppedReason}
        </p>
      )}
      {stopError && (
        <p className="border-b border-border px-2 py-1 text-xs text-critical">{stopError}</p>
      )}
      {monitor.status === "error" && (
        <p className="border-b border-border px-2 py-1 text-xs text-critical">
          {monitor.error}
          <button
            type="button"
            onClick={monitor.reload}
            className="ml-3 rounded border border-border px-2 py-0.5 text-xs text-ink hover:bg-panel-strong"
          >
            Watch again
          </button>
        </p>
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
            />
          ) : (
            <RunSummary run={run} steps={steps} calls={toolCalls} />
          )}
        </div>
      </div>
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
}: {
  step: TeamRunStep;
  role: string | null;
  calls: TeamRunToolCall[];
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

      <section className="flex min-h-0 flex-col gap-1">
        <h4 className="text-xs uppercase tracking-wide text-ink-faint">Output</h4>
        {step.output ? (
          <p className="whitespace-pre-wrap text-xs text-ink">{step.output}</p>
        ) : (
          <p className="text-xs text-ink-muted">
            {step.status === "pending" ? "waiting for its predecessors" : "nothing yet"}
          </p>
        )}
      </section>

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
}: {
  run: TeamRun | null;
  steps: TeamRunStep[];
  calls: TeamRunToolCall[];
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
    </>
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
