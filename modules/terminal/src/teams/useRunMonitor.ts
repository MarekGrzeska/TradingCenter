import { useCallback, useEffect, useRef, useState } from "react";
import {
  attachAgentKeys,
  type TeamRun,
  type TeamRunStep,
  type TeamRunToolCall,
  type TeamTrade,
} from "./runs";
import type { TeamsApi } from "./teamsApi";

/**
 * One run, watched. The stream is the whole source of truth and opens with a snapshot, so nothing polls and
 * reopening shows the run as it stands. The one read beside it is the calls recorded before the view arrived.
 */
export interface RunMonitor {
  status: "loading" | "watching" | "error";
  run: TeamRun | null;
  steps: TeamRunStep[];
  toolCalls: TeamRunToolCall[];
  /** What the run did to the account. Not on the stream — the module publishes progress,
   *  and an order is a row read back — so this is re-read whenever a call lands and once
   *  more when the run ends. */
  trades: TeamTrade[];
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
  const [trades, setTrades] = useState<TeamTrade[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  // Read once per connection, and only after the first snapshot: the steps it needs to
  // resolve a call's agent are in that snapshot.
  const recordedRead = useRef(false);
  // The steps as the last snapshot named them, kept in a ref rather than read from state: the read at the
  // end of a run happens inside the stream loop, where `steps` is the value it closed over.
  const stepsSeen = useRef<TeamRunStep[]>([]);
  // One trades read at a time: three agents calling at once would start three reads of the same list, and
  // the last to answer would not be the last to have been asked.
  const tradesInFlight = useRef(false);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    setStatus("loading");
    setError(null);
    recordedRead.current = false;
    stepsSeen.current = [];
    tradesInFlight.current = false;

    async function watch() {
      const events = await api.watchRun(runId, controller.signal);
      // The module closes the stream itself once the run is over, and only then. A body that ends earlier
      // is a dropped connection and has to be said — silence here reads like an agent thinking.
      let over = false;
      let working = true;
      for await (const event of events) {
        if (cancelled) return;
        if (event.kind === "snapshot") {
          working = event.run.status === "pending" || event.run.status === "running";
        }
        if (event.kind === "runFinished") over = true;
        switch (event.kind) {
          case "snapshot":
            setRun(event.run);
            setSteps(event.steps);
            stepsSeen.current = event.steps;
            setStatus("watching");
            if (!recordedRead.current) {
              recordedRead.current = true;
              void readRecordedCalls(event.steps);
            }
            void readTrades();
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
            // A trade is written by a call, so a call is the only moment one can appear. The event says a
            // tool was called, the row says what it did to the account, and the second is not in the first.
            void readTrades();
            break;
          case "runFinished":
            setRun((current) =>
              current === null
                ? current
                : { ...current, status: event.status, stoppedReason: event.stoppedReason },
            );
            // The recorded rows again, and complete this time: a call arriving on the stream carries no
            // arguments and no answer, so watching from the start showed less than opening afterwards.
            void readRecordedCalls(stepsSeen.current, { replacing: true });
            // Once more at the end, because the last order's row is written as the reply
            // lands — which can be after the call event that started it.
            void readTrades();
            break;
        }
      }
      if (!cancelled && working && !over) {
        setError("the connection to the run was lost — it is still working, this view is not");
        setStatus("error");
      }
    }

    async function readRecordedCalls(
      known: TeamRunStep[],
      { replacing = false }: { replacing?: boolean } = {},
    ) {
      try {
        const recorded = await api.runToolCalls(runId, controller.signal);
        if (cancelled) return;
        const attached = attachAgentKeys(recorded, known);
        // Replacing rather than merging once the run is over: the rows are the whole of what happened, so
        // the stream's copies of the same calls would only be shown twice.
        setToolCalls((current) => (replacing ? attached : [...attached, ...current]));
      } catch {
      // The trace of calls is not what this view is for; the run's own progress is, and that is already
      // arriving. Failing the whole monitor over the older half of a side panel is the worse answer.
      }
    }

    async function readTrades() {
      if (tradesInFlight.current) return;
      tradesInFlight.current = true;
      try {
        const placed = await api.runTrades(runId, controller.signal);
        if (!cancelled) setTrades(placed);
      } catch {
      // The list the module already answered stays on screen. A module deployed before this route existed
      // answers 404, and a run that placed nothing is the same empty list — neither is worth failing over.
      } finally {
        tradesInFlight.current = false;
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
