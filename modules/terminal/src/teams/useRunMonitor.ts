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
 * Closing the view aborts the request and nothing more: the run holds no reference to any
 * of this, which is exactly the property the module was built for.
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
  // The steps as the last snapshot named them — which is all a recorded call needs to be
  // given an agent. Kept in a ref rather than read from state: the read at the end of a
  // run happens inside the stream loop, where `steps` is the value it closed over.
  const stepsSeen = useRef<TeamRunStep[]>([]);
  // One trades read at a time. A round of calls from three agents at once would otherwise
  // start three reads of the same list, and the last to answer would not be the last to
  // have been asked.
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
      // The module closes the stream itself once the run is over, and only then. A body
      // that ends while the run is still working is a dropped connection, and it has to be
      // said: the last snapshot stays on screen either way, so silence here reads exactly
      // like an agent thinking for a long time.
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
            // A trade is written by a call, so a call is the only moment one can appear.
            // Reading the list rather than deriving a row from the event: the event says
            // a tool was called, the row says what it did to the account, and the second
            // is not in the first.
            void readTrades();
            break;
          case "runFinished":
            setRun((current) =>
              current === null
                ? current
                : { ...current, status: event.status, stoppedReason: event.stoppedReason },
            );
            // The recorded rows again, and this time they are complete: the run will not
            // write another. Until now a call that arrived on the stream carried no
            // arguments and no answer — the frame does not send them — so an operator who
            // watched a run from the start could read less of it than one who opened it
            // afterwards, and the call they most want to read is the one that just failed
            // (specs/terminal-teams, "Zakończony przebieg pokazuje treść każdego
            // wywołania").
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
        // Replacing rather than merging once the run is over: the rows are the whole of
        // what happened, so the stream's copies of the same calls have nothing left to
        // add and would only be shown twice.
        setToolCalls((current) => (replacing ? attached : [...attached, ...current]));
      } catch {
        // The trace of calls is not what this view is for; the run's own progress is, and
        // that is already arriving. Failing the whole monitor over the older half of a
        // side panel would be the worse answer.
      }
    }

    async function readTrades() {
      if (tradesInFlight.current) return;
      tradesInFlight.current = true;
      try {
        const placed = await api.runTrades(runId, controller.signal);
        if (!cancelled) setTrades(placed);
      } catch {
        // The list the module already answered stays on screen. A module deployed before
        // this route existed answers 404 here, and a run that placed nothing is the same
        // empty list either way — neither is worth failing the monitor over, whose job is
        // the run's own progress.
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
