import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router";
import { agentActivity, type AgentActivityStore } from "../agent/agentActivity";
import { resolveEndpoints } from "../data/config";
import { workbenchIdentity } from "../data/marketData";
import { messageOf, useRead } from "../data/query";
import { MarketDataError } from "../data/types";
import { BackButton } from "../ui/BackButton";
import { Button } from "../ui/Button";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { UnreachableNotice } from "../ui/UnreachableNotice";
import { ComparePanel } from "./ComparePanel";
import { anyPending, interval, runsGoing } from "./present";
import { ReportPanel } from "./ReportPanel";
import { RunForm } from "./RunForm";
import { RunsPanel } from "./RunsPanel";
import {
  createStrategiesApi,
  Refused,
  type ComparedRun,
  type Health,
  type Revision,
  type RunItem,
  type StrategiesApi,
  type StrategyItem,
} from "./strategiesApi";

/**
 * Backtests of every strategy (`terminal-strategies`, „Backtesty mają własną zakładkę”): runs side by side whatever
 * strategy they are of, the run form of the strategy picked, and a run's report. Writing a strategy is the Strategies
 * tab's; `?strategy=` is how it sends the operator here with one picked.
 */

const signal = () => new AbortController().signal;
const RUNS_POLL_MS = 3_000;
const MAX_COMPARED = 5;

export function BacktestsView({
  api,
  activity = agentActivity,
}: { api?: StrategiesApi; activity?: AgentActivityStore } = {}) {
  const client = useMemo(() => api ?? createStrategiesApi(resolveEndpoints().strategiesHttp, workbenchIdentity), [api]);
  const [params, setParams] = useSearchParams();
  const picked = Number(params.get("strategy")) || null;
  const [pickedRun, setPickedRun] = useState<number | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  // Ids, not rows: a comparison may hold runs of several strategies and survives switching the list's filter.
  // One selection for comparing and for deleting: two boxes a row was two unlabelled grey squares on a dark screen.
  const [selected, setSelected] = useState<ReadonlySet<number>>(new Set());
  const [deleting, setDeleting] = useState(false);
  const [compared, setCompared] = useState<{ runs: ComparedRun[] | null; refusal: string[] | null } | null>(null);

  const health = useRead<{ present: boolean; health: Health | null }>({
    key: ["strategies", "health"],
    read: async (s) => {
      try {
        return { present: true, health: await client.health(s) };
      } catch (cause: unknown) {
        if (cause instanceof MarketDataError && cause.kind === "not-found") return { present: false, health: null };
        throw cause;
      }
    },
    initial: { present: true, health: null },
    fallbackMessage: "nie udało się zapytać pakietu strategii",
  });
  const ready = health.status === "ready" && health.value.present;

  const list = useRead<StrategyItem[]>({
    key: ["strategies", "list", false],
    read: (s) => client.strategies(false, s),
    initial: [],
    fallbackMessage: "nie udało się wczytać strategii",
    enabled: ready,
  });
  const detail = useRead<Revision | null>({
    key: ["strategies", "detail", picked],
    read: async (s) => (await client.detail(picked as number, s)).revision,
    initial: null,
    fallbackMessage: "nie udało się wczytać strategii",
    enabled: ready && picked !== null,
  });
  const [pending, setPending] = useState(false);
  const runs = useRead<RunItem[]>({
    key: ["strategies", "runs", picked],
    read: (s) => client.runs(picked, s),
    initial: [],
    fallbackMessage: "nie udało się wczytać uruchomień",
    enabled: ready,
    // Only while something waits or computes: an idle tab asks nothing (db-cost-check).
    pollMs: pending ? RUNS_POLL_MS : undefined,
  });
  useEffect(() => setPending(anyPending(runs.value)), [runs.value]);

  // The agent may have queued a run in a turn.
  useEffect(
    () =>
      activity.subscribe(() => {
        runs.reload();
        list.reload();
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [activity],
  );

  const run = runs.value.find((r) => r.id === pickedRun) ?? null;
  // The report is drawn on the chart of the strategy the run is of, at the revision it was made of.
  const ofRun = useRead<Revision | null>({
    key: ["strategies", "revision", run?.strategyId, run?.revision],
    read: (s) => client.revision(run!.strategyId, run!.revision, s),
    initial: null,
    fallbackMessage: "nie udało się wczytać rewizji uruchomienia",
    enabled: ready && run !== null,
  });

  if (health.status === "ready" && !health.value.present) {
    return (
      <section className="flex h-full min-h-0 flex-col gap-3 p-4">
        <h1 className="text-base font-semibold text-ink">Backtesty</h1>
        <p className="text-sm text-ink-muted">
          Ten workbench nie ma pakietu strategii: <code>STRATEGIES_DATABASE_URL</code> nie jest ustawione.
        </p>
      </section>
    );
  }

  const names = new Map(list.value.map((s) => [s.id, s.name]));

  function toggleSelected(id: number) {
    const next = new Set(selected);
    if (!next.delete(id)) next.add(id);
    setSelected(next);
  }

  async function deleteSelected() {
    const ids = [...selected];
    try {
      await client.deleteRuns(ids, signal());
    } catch (cause: unknown) {
      // Said in the dialog that asked, which stays open: nothing was deleted.
      throw cause instanceof Refused ? new Error(cause.problems.map((p) => p.message).join("; ")) : cause;
    }
    setSelected(new Set());
    setCompared(null);
    if (pickedRun !== null && ids.includes(pickedRun)) setPickedRun(null);
    runs.reload();
    list.reload();
  }

  const unfinished = [...selected].some((id) => runs.value.find((r) => r.id === id)?.status !== "done");
  const compareBlocked =
    selected.size === 0
      ? `zaznacz od 2 do ${MAX_COMPARED} zakończonych uruchomień, żeby je porównać, albo dowolne, żeby je usunąć`
      : unfinished
        ? "porównać można tylko zakończone uruchomienia"
        : selected.size < 2 || selected.size > MAX_COMPARED
          ? `porównanie bierze od 2 do ${MAX_COMPARED} uruchomień`
          : null;

  async function compare() {
    setFailure(null);
    try {
      setCompared({ runs: await client.compare([...selected], signal()), refusal: null });
    } catch (cause: unknown) {
      if (cause instanceof Refused) setCompared({ runs: null, refusal: cause.problems.map((p) => p.message) });
      else setFailure(messageOf(cause, "nie udało się porównać uruchomień"));
    }
  }
  const document = detail.value?.document as { symbol?: string; params?: Record<string, never> } | undefined;
  const runDocument = ofRun.value?.document as { symbol?: string; timeframe?: string } | undefined;

  return (
    <section className="flex h-full min-h-0 flex-col gap-3 overflow-y-auto p-3">
      <header className="flex flex-wrap items-center gap-3">
        {picked !== null && (
          <BackButton
            label="Wszystkie backtesty"
            size="xs"
            onClick={() => {
              setPickedRun(null);
              setFailure(null);
              setParams({});
            }}
          />
        )}
        <h1 className="text-base font-semibold text-ink">Backtesty</h1>
        <label className="flex items-center gap-2 text-xs text-ink-secondary">
          Strategia
          <select
            aria-label="Strategia"
            className="rounded border border-border bg-sunken px-2 py-1 text-sm text-ink"
            value={picked ?? ""}
            onChange={(e) => {
              setPickedRun(null);
              setFailure(null);
              setParams(e.target.value === "" ? {} : { strategy: e.target.value });
            }}
          >
            <option value="">wszystkie</option>
            {list.value.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name} · {s.symbol} · {interval(s.timeframe)}
              </option>
            ))}
          </select>
        </label>
      </header>
      {health.error !== null && <UnreachableNotice onRetry={health.reload}>{health.error}</UnreachableNotice>}
      {list.error !== null && <p className="text-xs text-critical">{list.error}</p>}
      {failure !== null && (
        <p role="alert" className="text-sm text-critical">
          {failure}
        </p>
      )}

      {picked === null ? (
        <p className="text-sm text-ink-muted">Wybierz strategię, żeby uruchomić backtest. Poniżej uruchomienia wszystkich strategii.</p>
      ) : (
        detail.value !== null && (
          <RunForm
            key={`${detail.value.strategyId}-${detail.value.n}`}
            api={client}
            strategyId={detail.value.strategyId}
            revision={detail.value.n}
            symbol={document?.symbol ?? ""}
            params={(document?.params ?? {}) as never}
            execution={detail.value.execution ?? "MINUTE"}
            maxExecutionBars={health.value.health?.maxExecutionBars ?? null}
            onQueued={() => runs.reload()}
          />
        )
      )}

      <div className="flex flex-wrap items-center gap-2 text-xs text-ink-secondary">
        <Button size="2xs" disabled={compareBlocked !== null} onClick={() => void compare()}>
          Porównaj ({selected.size})
        </Button>
        <Button size="2xs" tone="critical" disabled={selected.size === 0} onClick={() => setDeleting(true)}>
          Usuń ({selected.size})
        </Button>
        {selected.size > 0 && (
          <Button
            size="2xs"
            tone="muted"
            onClick={() => {
              setSelected(new Set());
              setCompared(null);
            }}
          >
            Wyczyść
          </Button>
        )}
        {compareBlocked !== null && <span>{compareBlocked}</span>}
      </div>
      {deleting && (
        <ConfirmDialog
          title="Usuń uruchomienia"
          confirmLabel="Usuń"
          cancelLabel="Anuluj"
          busyLabel="Usuwam…"
          tone="danger"
          fallbackError="nie udało się usunąć uruchomień"
          onConfirm={deleteSelected}
          onClose={() => setDeleting(false)}
        >
          <p className="text-xs text-ink-secondary">
            {runsGoing(selected.size)}, razem z raportem i transakcjami. Nie da się tego cofnąć. Licznik prób strategii zostaje taki, jaki był.
          </p>
        </ConfirmDialog>
      )}
      {compared !== null && <ComparePanel runs={compared.runs} refusal={compared.refusal} strategyNames={names} />}

      <RunsPanel
        runs={runs.value}
        selected={selected}
        onSelect={toggleSelected}
        error={runs.error}
        picked={pickedRun}
        onPick={setPickedRun}
        strategyNames={picked === null ? names : undefined}
        onCancel={async (id) => {
          setFailure(null);
          try {
            await client.cancel(id, signal());
            runs.reload();
          } catch (cause: unknown) {
            setFailure(messageOf(cause, "nie udało się anulować uruchomienia"));
          }
        }}
      />
      {run !== null && runDocument !== undefined && (
        <BackButton label="Uruchomienia" size="xs" onClick={() => setPickedRun(null)} />
      )}
      {run !== null && runDocument !== undefined && (
        <ReportPanel
          key={run.id}
          api={client}
          runId={run.id}
          symbol={runDocument.symbol ?? ""}
          timeframe={runDocument.timeframe ?? "HOUR"}
        />
      )}
    </section>
  );
}
