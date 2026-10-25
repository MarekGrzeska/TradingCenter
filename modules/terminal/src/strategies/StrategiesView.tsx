import { useEffect, useMemo, useRef, useState } from "react";
import { agentActivity, type AgentActivityStore } from "../agent/agentActivity";
import type { AgentChatStore } from "../agent/agentChatStore";
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
  type Draft,
  type Revision,
  type RunItem,
  type StrategiesApi,
  type StrategyItem,
} from "./strategiesApi";
import { StrategyChat } from "./StrategyChat";
import { createStrategyChatStore } from "./strategyChatStore";
import { StrategyEditor } from "./StrategyEditor";
import { SummaryPanel } from "./SummaryPanel";
import { useLiveValidation } from "./useLiveValidation";

/**
 * Strategies as documents (`terminal-strategies`): the operator reads what the agent wrote and the summary read back from
 * it, corrects it by hand, runs it and reads the report. Beside the editor is the strategy's own conversation with the
 * agent; the terminal's panel is told which strategy is open too. Everything is read again once a turn ends — the tab
 * never interprets the agent's tool calls.
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

/** Which strategy the chat's conversation belongs to: its id, or "new" for one begun before the strategy existed. */
type ChatOwner = { strategy: number | "new"; name: string; conversation: number | null } | null;

export function StrategiesView({
  api,
  activity = agentActivity,
  pairs = archive,
  chat: chatStore,
}: { api?: StrategiesApi; activity?: AgentActivityStore; pairs?: ArchiveAdmin; chat?: AgentChatStore } = {}) {
  const client = useMemo(() => api ?? createStrategiesApi(resolveEndpoints().strategiesHttp, workbenchIdentity), [api]);
  const chat = useMemo(() => chatStore ?? createStrategyChatStore(activity), [chatStore, activity]);
  const chatOwner = useRef<ChatOwner>(null);
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

  async function assignConversation(strategyId: number, conversation: number, name: string) {
    try {
      await client.setConversation(strategyId, conversation, signal());
      chat.renameSession(conversation, name);
      list.reload();
    } catch {
      // The conversation stays on screen; only reopening the strategy elsewhere would start a new one.
    }
  }

  /** The strategy's own conversation, or the one begun for it while it did not exist yet, or a new one. */
  function attachChat(item: StrategyItem) {
    const owner = chatOwner.current;
    const session = chat.getSnapshot().activeSessionId;
    chatOwner.current = { strategy: item.id, name: item.name, conversation: item.conversationId };
    if (item.conversationId !== null) {
      chat.openSession(item.conversationId);
    } else if (owner?.strategy === "new" && session !== null) {
      chatOwner.current.conversation = session;
      void assignConversation(item.id, session, item.name);
    } else {
      chat.newSession();
    }
  }

  // A conversation the chat creates on its first message belongs to the strategy it was begun for.
  useEffect(() => {
    let before = chat.getSnapshot().activeSessionId;
    return chat.subscribe(() => {
      const now = chat.getSnapshot().activeSessionId;
      const created = before === null && now !== null;
      before = now;
      const owner = chatOwner.current;
      if (!created || now === null || owner === null || owner.strategy === "new" || owner.conversation !== null) return;
      owner.conversation = now;
      void assignConversation(owner.strategy, now, owner.name);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chat]);

  async function open(id: number) {
    setFailure(null);
    setNotice(null);
    setCreating(false);
    setPickedRun(null);
    try {
      const { item, revision } = await client.detail(id, signal());
      load(revision);
      setOpenId(id);
      attachChat(item);
      const draft = await client.draft(id, signal());
      if (draft !== null && draft.updatedAt > revision.createdAt) showDraft(draft);
    } catch (cause: unknown) {
      setFailure(messageOf(cause, "nie udało się otworzyć strategii"));
    }
  }

  // The agent's draft last put into the editor: a later read showing the same `seq` is not news, and a revision the agent
  // saves while the editor still holds exactly this text replaces it rather than being reported as newer.
  const shownDraft = useRef<{ seq: number; text: string } | null>(null);

  function showDraft(draft: Draft) {
    const shown = documentText(draft.document);
    shownDraft.current = { seq: draft.seq, text: shown };
    setText(shown);
    setNewer(null);
    setNotice("Agent wpisał zmianę do edytora — jest niezapisana: zapisz ją albo porzuć.");
  }

  async function discardDraft() {
    shownDraft.current = null;
    try {
      await client.discardDraft(base?.strategyId ?? null, signal());
    } catch {
      // A draft left behind is shown again only if it is newer than the revision, so nothing is lost by failing here.
    }
  }

  // Read after every turn: the agent may have saved a revision, created a strategy or queued a run.
  const latestState = useRef({ openId, base, dirty, text, creating, list: list.value });
  latestState.current = { openId, base, dirty, text, creating, list: list.value };
  useEffect(
    () =>
      activity.subscribe(() => {
        const { openId: id, base: at, dirty, text: onScreen, creating: isNew, list: known } = latestState.current;
        // Text that is the agent's own draft is not the operator's unsaved work.
        const unsaved = dirty && onScreen !== shownDraft.current?.text;
        list.reload();
        runs.reload();
        void (async () => {
          try {
            if (id !== null && at !== null) {
              const latest = await client.revision(id, null, signal());
              const next = afterTurn({ strategyId: id, base: at.n, dirty: unsaved }, latest.n);
              if (next.kind === "load") {
                load(latest);
                shownDraft.current = null;
                setNotice(latest.author === "agent" ? `Agent zapisał rewizję ${latest.n}.` : `Wczytano rewizję ${latest.n}.`);
              } else if (next.kind === "newer") {
                setNewer(next.revision);
              }
              const draft = await client.draft(id, signal());
              if (draft !== null && draft.seq !== shownDraft.current?.seq) showDraft(draft);
              return;
            }
            if (isNew) {
              const draft = await client.draft(null, signal());
              if (draft !== null && draft.seq !== shownDraft.current?.seq) showDraft(draft);
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
              chatOwner.current = { strategy: "new", name: "", conversation: null };
              chat.newSession();
              shownDraft.current = null;
              void client.discardDraft(null, signal()).catch(() => {});
              setNotice("Nowa strategia: opisz ją w czacie obok albo popraw szkielet.");
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
            Wybierz strategię z listy albo kliknij „Nowa…” i opisz ją w czacie obok edytora.
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
                <Button
                  size="xs"
                  tone="muted"
                  onClick={() => {
                    setText(baseText);
                    void discardDraft();
                  }}
                >
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
            <div className="grid h-[30rem] min-h-0 shrink-0 grid-cols-[minmax(0,1fr)_minmax(22rem,1fr)] gap-3">
              <StrategyEditor
                text={text}
                onChange={setText}
                checked={validation.checked}
                language={language.value}
                symbols={symbols.value}
              />
              <StrategyChat store={chat} />
            </div>
            <SummaryPanel summary={validation.summary ?? base?.summary ?? null} valid={validation.valid} stale={validation.stale && dirty} />

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
