import { useCallback, useEffect, useRef, useState } from "react";
import {
  attachAgentKeys,
  type TeamRun,
  type TeamRunStep,
  type TeamRunToolCall,
  type TeamRunTrade,
} from "./runs";
import type { TeamsApi } from "./teamsApi";

/**
 * One run, watched.
 *
 * The stream is the whole source of truth while it lasts, and it opens with a snapshot of
 * where the run is now — so opening this view halfway through, or closing and opening it
 * again, shows the run as it stands rather than as it was (specs/teams-runs, "po ponownym
 * otwarciu widać jego bieżący stan"). Nothing here polls.
 *
 * The one read beside it is the tool calls already recorded before this view arrived. They
 * are not in the snapshot — the module sends the steps, and a call is a row under a step —
 * so they are fetched once, after the snapshot names the steps to attach them to. Calls
 * that happen while watching arrive on the stream and are appended.
 *
 * **Trades are read rather than streamed, and re-read on each tool call.** The module
 * publishes no trade event: an order *is* a tool call, and the stream frame carries the
 * name and the outcome but not the symbol, the size or the provider's order id, which
 * are the columns the row exists for. So the signal to re-read is the tool-call event
 * itself — a read when something happened, not a timer — and the run's own progress
 * never waits on it.
 *
 * Closing the view aborts the request and nothing more: the run holds no reference to any
 * of this, which is exactly the property the module was built for.
 */
export interface RunMonitor {
  status: "loading" | "watching" | "error";
  run: TeamRun | null;
  steps: TeamRunStep[];
  toolCalls: TeamRunToolCall[];
  /** Every order this run has placed, newest read wins — see the note above on why
   *  these are read rather than streamed. */
  trades: TeamRunTrade[];
  error: string | null;
  /** Opens the stream again — after a dropped connection, and after the operator asked
   *  the run to stop, so the view is never left guessing. */
  reload(): void;
}

export function useRunMonitor(api: TeamsApi, runId: number): RunMonitor {
  const [status, setStatus] = useState<RunMonitor["status"]>("loading");
  const [run, setRun] = useState<TeamRun | null>(null);
  const [steps, setSteps] = useState<TeamRunStep[]>([]);
  const [toolCalls, setToolCalls] = useState<TeamRunToolCall[]>([]);
  const [trades, setTrades] = useState<TeamRunTrade[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  // Read once per connection, and only after the first snapshot: the steps it needs to
  // resolve a call's agent are in that snapshot.
  const recordedRead = useRef(false);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    setStatus("loading");
    setError(null);
    recordedRead.current = false;

    async function watch() {
      const events = await api.watchRun(runId, controller.signal);
      for await (const event of events) {
        if (cancelled) return;
        switch (event.kind) {
          case "snapshot":
            setRun(event.run);
            setSteps(event.steps);
            setStatus("watching");
            if (!recordedRead.current) {
              recordedRead.current = true;
              void readRecordedCalls(event.steps);
              void readTrades();
            }
            break;
          case "stepStarted":
            setSteps((current) => patchStep(current, event.agentKey, { status: "running" }));
            break;
          case "stepFinished":
            setSteps((current) =>
              patchStep(current, event.agentKey, {
                status: event.status,
                output: event.output,
              }),
            );
            break;
          case "toolCall":
            setToolCalls((current) => [...current, event.call]);
            // A call may have been an order, and only the row knows what it placed.
            void readTrades();
            break;
          case "runFinished":
            // Once more at the end: the last order's own result is written as the call
            // resolves, which can land after the event that announced the call.
            void readTrades();
            setRun((current) =>
              current === null
                ? current
                : { ...current, status: event.status, stoppedReason: event.stoppedReason },
            );
            break;
        }
      }
    }

    async function readTrades() {
      try {
        const placed = await api.runTrades(runId, controller.signal);
        if (!cancelled) setTrades(placed);
      } catch {
        // Same reasoning as the recorded calls below: the run's progress is what this
        // view is for, and it is already arriving.
      }
    }

    async function readRecordedCalls(known: TeamRunStep[]) {
      try {
        const recorded = await api.runToolCalls(runId, controller.signal);
        if (cancelled) return;
        // Ahead of whatever the stream has already appended, in the order they were made.
        setToolCalls((current) => [...attachAgentKeys(recorded, known), ...current]);
      } catch {
        // The trace of calls is not what this view is for; the run's own progress is, and
        // that is already arriving. Failing the whole monitor over the older half of a
        // side panel would be the worse answer.
      }
    }

    watch().catch((cause: unknown) => {
      if (cancelled || controller.signal.aborted) return;
      setError(cause instanceof Error ? cause.message : "the run could not be watched");
      setStatus("error");
    });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [api, runId, attempt]);

  return {
    status,
    run,
    steps,
    toolCalls,
    trades,
    error,
    reload: useCallback(() => {
      setToolCalls([]);
      setTrades([]);
      setAttempt((n) => n + 1);
    }, []),
  };
}

function patchStep(
  steps: TeamRunStep[],
  agentKey: string,
  patch: Partial<TeamRunStep>,
): TeamRunStep[] {
  return steps.map((step) => (step.agentKey === agentKey ? { ...step, ...patch } : step));
}
