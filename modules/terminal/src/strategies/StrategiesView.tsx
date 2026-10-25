import { useEffect, useMemo, useRef, useState } from "react";
import { agentActivity, type AgentActivityStore } from "../agent/agentActivity";
import { setStrategyInView } from "../agent/strategyInView";
import { resolveEndpoints } from "../data/config";
import { archive, workbenchIdentity } from "../data/marketData";
import { messageOf, useRead } from "../data/query";
import type { ArchiveAdmin } from "../data/source";
import { MarketDataError } from "../data/types";
import { Button } from "../ui/Button";
import { UnreachableNotice } from "../ui/UnreachableNotice";
import { afterTurn, createdDuringTurn, documentText } from "./followTurn";
import { HistoryPanel } from "./HistoryPanel";
import { anyPending, interval } from "./present";
import { ReportPanel } from "./ReportPanel";
import { RunForm } from "./RunForm";
import { RunsPanel } from "./RunsPanel";
import {
  createStrategiesApi,
  Refused,
  SaveConflict,
  type Health,
  type Language,
  type Revision,
  type RunItem,
  type StrategiesApi,
  type StrategyItem,
} from "./strategiesApi";
import { StrategyEditor } from "./StrategyEditor";
import { SummaryPanel } from "./SummaryPanel";
import { useLiveValidation } from "./useLiveValidation";

/**
 * Strategies as documents (`terminal-strategies`): the operator reads what the agent wrote and the summary read back from
 * it, corrects it by hand, runs it and reads the report. The agent is the terminal's own panel; this tab tells it which
 * strategy is open and reads everything again once a turn ends — it never interprets the agent's tool calls.
 */

const signal = () => new AbortController().signal;
const RUNS_POLL_MS = 3_000;

const BLANK = {
  schema: 1,
  name: "Nowa strategia",
  hypothesis: "",
  notes: "",
  symbol: "US100",
  timeframe: "HOUR",
  params: {},
  let: {},
  entries: [{ side: "long", when: "", order: { type: "market" } }],
  exits: { stop: "" },
  sizing: { mode: "risk_fraction", value: 0.005 },
  limits: {},
};

type Pane = "history" | "runs";

export function StrategiesView({
  api,
  activity = agentActivity,
  pairs = archive,
}: { api?: StrategiesApi; activity?: AgentActivityStore; pairs?: ArchiveAdmin } = {}) {
  const client = useMemo(() => api ?? createStrategiesApi(resolveEndpoints().strategiesHttp, workbenchIdentity), [api]);
  const [archived, setArchived] = useState(false);
  const [openId, setOpenId] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const [base, setBase] = useState<Revision | null>(null);
  const [text, setText] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [newer, setNewer] = useState<number | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [pane, setPane] = useState<Pane>("runs");
  const [pickedRun, setPickedRun] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

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
  const present = health.value.present;
  const ready = health.status === "ready" && present;

  const list = useRead<StrategyItem[]>({
    key: ["strategies", "list", archived],
    read: (s) => client.strategies(archived, s),
    initial: [],
    fallbackMessage: "nie udało się wczytać strategii",
    enabled: ready,
  });
  const language = useRead<Language | null>({
    key: ["strategies", "language"],
    read: (s) => client.language(s),
    initial: null,
    fallbackMessage: "nie udało się wczytać opisu języka",
    enabled: ready,
  });
  const symbols = useRead<string[]>({
    key: ["strategies", "symbols"],
    read: async (s) => [...new Set((await pairs.listPairs(s)).map((p) => p.symbol))].sort(),
    initial: [],
    fallbackMessage: "nie udało się wczytać instrumentów archiwum",
    enabled: ready,
  });
  const [runsPending, setRunsPending] = useState(false);
  const runs = useRead<RunItem[]>({
    key: ["strategies", "runs", openId],
    read: (s) => client.runs(openId as number, s),
    initial: [],
    fallbackMessage: "nie udało się wczytać uruchomień",
    enabled: ready && openId !== null,
    // Only while something waits or computes: an idle tab asks nothing (db-cost-check).
    pollMs: runsPending ? RUNS_POLL_MS : undefined,
  });
  useEffect(() => setRunsPending(anyPending(runs.value)), [runs.value]);

  const baseText = base === null ? (creating ? documentText(BLANK) : "") : documentText(base.document);
  const dirty = (base !== null || creating) && text !== baseText;
  const editing = base !== null || creating;
  const validation = useLiveValidation(client, text, ready && editing);

  // What the panel sends with a turn while this tab is on screen.
  useEffect(() => {
    setStrategyInView(
      editing ? { strategyId: base?.strategyId ?? null, revision: base?.n ?? null, draft: dirty ? text : null } : null,
    );
  }, [editing, base, dirty, text]);
  useEffect(() => () => setStrategyInView(null), []);

  function load(revision: Revision) {
    setBase(revision);
    setText(documentText(revision.document));
    setNewer(null);
  }

  async function open(id: number) {
    setFailure(null);
    setNotice(null);
    setCreating(false);
    setPickedRun(null);
    try {
      load(await client.revision(id, null, signal()));
      setOpenId(id);
    } catch (cause: unknown) {
      setFailure(messageOf(cause, "nie udało się otworzyć strategii"));
    }
  }

  // Read after every turn: the agent may have saved a revision, created a strategy or queued a run.
  const latestState = useRef({ openId, base, dirty, list: list.value });
  latestState.current = { openId, base, dirty, list: list.value };
  useEffect(
    () =>
      activity.subscribe(() => {
        const { openId: id, base: at, dirty: unsaved, list: known } = latestState.current;
        list.reload();
        runs.reload();
        void (async () => {
          try {
            if (id !== null && at !== null) {
              const latest = await client.revision(id, null, signal());
              const next = afterTurn({ strategyId: id, base: at.n, dirty: unsaved }, latest.n);
              if (next.kind === "load") {
                load(latest);
                setNotice(latest.author === "agent" ? `Agent zapisał rewizję ${latest.n}.` : `Wczytano rewizję ${latest.n}.`);
              } else if (next.kind === "newer") {
                setNewer(next.revision);
              }
              return;
            }
            const now = await client.strategies(false, signal());
            const created = createdDuringTurn(new Set(known.map((s) => s.id)), now, id !== null);
            if (created !== null) {
              await open(created);
              setNotice("Agent utworzył tę strategię.");
            }
          } catch {
            // The next turn, or a click, reads again; a failed re-read must not disturb the editor.
          }
        })();
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [activity, client],
  );

  async function save() {
    setSaving(true);
    setFailure(null);
    setNotice(null);
    try {
      const document = JSON.parse(text) as unknown;
      if (base === null) {
        const created = await client.create(document, signal());
        await open(created.strategyId);
      } else {
        const saved = await client.save(base.strategyId, document, base.n, signal());
        load(await client.revision(base.strategyId, saved.revision, signal()));
        setNotice(saved.created ? `Zapisano rewizję ${saved.revision}.` : "Treść równa ostatniej rewizji — nic nowego nie powstało.");
      }
      list.reload();
    } catch (cause: unknown) {
      if (cause instanceof SaveConflict) setNewer(cause.latest);
      else if (cause instanceof Refused) setFailure(`${cause.message} — szczegóły przy miejscach w edytorze.`);
      else setFailure(messageOf(cause, "nie udało się zapisać"));
    } finally {
      setSaving(false);
    }
  }

  async function restore(n: number) {
    if (base === null) return;
    const old = await client.revision(base.strategyId, n, signal());
    const saved = await client.save(base.strategyId, old.document, base.n, signal());
    load(await client.revision(base.strategyId, saved.revision, signal()));
    setNotice(`Rewizja ${n} przywrócona jako rewizja ${saved.revision}.`);
    list.reload();
  }

  async function act(work: () => Promise<unknown>, fallback: string) {
    setFailure(null);
    try {
      await work();
      list.reload();
      runs.reload();
    } catch (cause: unknown) {
      setFailure(messageOf(cause, fallback));
    }
  }

  if (health.status === "ready" && !present) {
    return (
      <section className="flex h-full min-h-0 flex-col gap-3 p-4">
        <h1 className="text-base font-semibold text-ink">Strategie</h1>
        <p className="text-sm text-ink-muted">
          Ten workbench nie ma pakietu strategii: <code>STRATEGIES_DATABASE_URL</code> nie jest ustawione, więc pakiet nie jest
          częścią procesu. To działająca konfiguracja, nie awaria.
        </p>
      </section>
    );
  }

  const open_ = list.value.find((s) => s.id === openId) ?? null;
  const valid = validation.valid === true && !validation.stale;
  const document = base?.document as { symbol?: string; timeframe?: string; params?: Record<string, never> } | undefined;

  return (
    <section className="flex h-full min-h-0 gap-3 p-3">
      <aside aria-label="Strategie" className="flex w-60 shrink-0 flex-col gap-2 overflow-y-auto">
        <div className="flex items-center gap-2">
          <h1 className="text-base font-semibold text-ink">Strategie</h1>
          <Button
            size="xs"
            tone="primary"
            disabled={!ready}
            onClick={() => {
              setOpenId(null);
              setBase(null);
              setCreating(true);
              setText(documentText(BLANK));
              setNotice("Nowa strategia: popraw szkielet albo opisz strategię w panelu agenta.");
            }}
          >
            Nowa…
          </Button>
        </div>
        <label className="flex items-center gap-1 text-xs text-ink-muted">
          <input type="checkbox" checked={archived} onChange={(e) => setArchived(e.target.checked)} /> zarchiwizowane
        </label>
        {health.error !== null && <UnreachableNotice onRetry={health.reload}>{health.error}</UnreachableNotice>}
        {list.error !== null && <p className="text-xs text-critical">{list.error}</p>}
        {list.status === "ready" && list.value.length === 0 && (
          <p className="text-xs text-ink-muted">{archived ? "Nic nie jest zarchiwizowane." : "Nie ma jeszcze strategii."}</p>
        )}
        <ul className="space-y-1">
          {list.value.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                onClick={() => void open(s.id)}
                className={`w-full rounded px-2 py-1 text-left text-xs ${s.id === openId ? "bg-panel-strong text-ink" : "text-ink-secondary hover:bg-panel"}`}
              >
                <span className="block font-semibold text-ink">{s.name}</span>
                {s.symbol} · {interval(s.timeframe)} · rew. {s.latestRevision} ({s.latestAuthor === "agent" ? "agent" : "operator"}) ·{" "}
                {s.trials} {s.trials === 1 ? "próba" : "prób"}
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col gap-3 overflow-y-auto">
        {!editing ? (
          <p className="text-sm text-ink-muted">
            Wybierz strategię z listy albo opisz nową w panelu agenta — po jego odpowiedzi otworzy się tutaj.
          </p>
        ) : (
          <>
            <header className="flex flex-wrap items-center gap-2">
              <h2 className="text-sm font-semibold text-ink">
                {base === null ? "Nowa strategia" : `${open_?.name ?? ""} · rewizja ${base.n} (${base.author === "agent" ? "agent" : "operator"})`}
              </h2>
              {open_ !== null && <span className="text-xs text-ink-faint">{open_.trials} prób</span>}
              {dirty && <span className="text-xs text-warning">niezapisane zmiany</span>}
              <Button size="xs" tone="primary" disabled={!valid || !dirty || saving} onClick={() => void save()}>
                Zapisz
              </Button>
              {dirty && (
                <Button size="xs" tone="muted" onClick={() => setText(baseText)}>
                  Porzuć zmiany
                </Button>
              )}
              {open_ !== null && (
                <Button
                  size="xs"
                  tone="muted"
                  onClick={() => void act(() => client.setArchived(open_.id, open_.archivedAt === null, signal()), "nie udało się")}
                >
                  {open_.archivedAt === null ? "Archiwizuj" : "Przywróć"}
                </Button>
              )}
            </header>
            {newer !== null && base !== null && (
              <p role="status" className="flex flex-wrap items-center gap-2 rounded bg-warning-soft px-3 py-1 text-sm text-warning">
                Istnieje nowsza rewizja {newer}. Twoje zmiany nie zostały zapisane.
                <Button size="2xs" onClick={() => void client.revision(base.strategyId, newer, signal()).then(load)}>
                  Wczytaj rewizję {newer} (porzuć moje zmiany)
                </Button>
                <Button size="2xs" tone="muted" onClick={() => setNewer(null)}>
                  Edytuj dalej
                </Button>
              </p>
            )}
            {notice !== null && <p className="text-sm text-ink-secondary">{notice}</p>}
            {failure !== null && (
              <p role="alert" className="text-sm text-critical">
                {failure}
              </p>
            )}
            {validation.failure !== null && <p className="text-xs text-critical">{validation.failure}</p>}
            <div className="grid h-[30rem] min-h-0 grid-cols-[minmax(0,3fr)_minmax(0,2fr)] gap-3">
              <StrategyEditor
                text={text}
                onChange={setText}
                checked={validation.checked}
                language={language.value}
                symbols={symbols.value}
              />
              <SummaryPanel summary={validation.summary ?? base?.summary ?? null} valid={validation.valid} stale={validation.stale && dirty} />
            </div>

            {base !== null && (
              <>
                <nav className="flex gap-2">
                  <Button size="xs" tone={pane === "runs" ? "primary" : "muted"} onClick={() => setPane("runs")}>
                    Uruchomienia
                  </Button>
                  <Button size="xs" tone={pane === "history" ? "primary" : "muted"} onClick={() => setPane("history")}>
                    Historia rewizji
                  </Button>
                </nav>
                {pane === "history" ? (
                  <HistoryPanel key={base.n} api={client} strategyId={base.strategyId} latest={base.n} onRestore={restore} />
                ) : (
                  <div className="flex flex-col gap-3">
                    <RunForm
                      key={`${base.strategyId}-${base.n}`}
                      api={client}
                      strategyId={base.strategyId}
                      revision={base.n}
                      symbol={document?.symbol ?? ""}
                      params={(document?.params ?? {}) as never}
                      maxMinuteBars={health.value.health?.maxMinuteBars ?? null}
                      onQueued={() => runs.reload()}
                    />
                    <RunsPanel
                      runs={runs.value}
                      error={runs.error}
                      picked={pickedRun}
                      onPick={setPickedRun}
                      onCancel={(id) => act(() => client.cancel(id, signal()), "nie udało się anulować uruchomienia")}
                    />
                    {pickedRun !== null && (
                      <ReportPanel
                        key={pickedRun}
                        api={client}
                        runId={pickedRun}
                        symbol={document?.symbol ?? ""}
                        timeframe={document?.timeframe ?? "HOUR"}
                      />
                    )}
                  </div>
                )}
              </>
            )}
          </>
        )}
      </div>
    </section>
  );
}
