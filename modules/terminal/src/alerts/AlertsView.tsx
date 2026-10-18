import { useMemo, useState } from "react";
import { resolveEndpoints } from "../data/config";
import { alertsIdentity } from "../data/marketData";
import { messageOf, useRead } from "../data/query";
import { MarketDataError } from "../data/types";
import { Button } from "../ui/Button";
import { UnreachableNotice } from "../ui/UnreachableNotice";
import {
  createAlertsApi,
  type AlertsApi,
  type Catalog,
  type Defect,
  type History,
  type PackageState,
  type Rule,
} from "./alertsApi";
import { DeleteRuleDialog, RuleDialog, type Start } from "./dialogs";
import { CHECK_LABEL, FIRE_LABEL, blankForm, describeSource, formFrom, statusOf, warnings } from "./present";

/**
 * Who is told what, and why not. **The question is "will I be told, and if not, why"**: every rule says what it watches in
 * one line, whether it is working, and — one click in — what became of it lately, including the times it could not look or
 * crossed its level inside its cool-down. What the package cannot do (no door to Telegram, no tools, a stopped clock) is said
 * at the top for as long as it is true.
 */

const POLL_MS = 30_000;
const signal = () => new AbortController().signal;
const TONE: Record<string, string> = {
  ok: "text-positive",
  warning: "text-warning",
  critical: "text-critical",
  muted: "text-ink-faint",
};

const NO_STATE: PackageState = {
  rulesEnabled: 0,
  rulesDisabled: 0,
  rulesWithDefects: 0,
  waitingFires: 0,
  delivering: true,
  drafting: false,
  readingValues: true,
  clock: { ran: true, ageSeconds: 0, expectedSeconds: 5 },
};

const NO_CATALOG: Catalog = {
  tools: [],
  eventTypes: [],
  recipients: [],
  gateway: true,
  minIntervalSeconds: 30,
  symbols: [],
  drafting: false,
};

interface StateRead {
  present: boolean;
  state: PackageState;
}

type Dialog =
  | { kind: "rule"; start: Start; editing?: Rule }
  | { kind: "delete"; rule: Rule };

export function AlertsView({ api }: { api?: AlertsApi } = {}) {
  const client = useMemo(() => api ?? createAlertsApi(resolveEndpoints().alertsHttp, alertsIdentity), [api]);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [sentence, setSentence] = useState("");
  const [drafting, setDrafting] = useState(false);
  const [unreadable, setUnreadable] = useState<{ understood: string; defects: Defect[] } | null>(null);
  const [open, setOpen] = useState<number | null>(null);

  const state = useRead<StateRead>({
    key: ["alerts", "state"],
    read: async (s) => {
      try {
        return { present: true, state: await client.state(s) };
      } catch (cause: unknown) {
        // Not "no rules" and not "unreachable": this workbench does not have the package.
        if (cause instanceof MarketDataError && cause.kind === "not-found") return { present: false, state: NO_STATE };
        throw cause;
      }
    },
    initial: { present: true, state: NO_STATE },
    fallbackMessage: "nie udało się wczytać stanu pakietu alertów",
    pollMs: POLL_MS,
  });
  const present = state.value.present;

  const rules = useRead<Rule[]>({
    key: ["alerts", "rules"],
    read: (s) => client.rules(s),
    initial: [],
    fallbackMessage: "nie udało się wczytać reguł",
    pollMs: POLL_MS,
    enabled: state.status === "ready" && present,
  });
  const catalog = useRead<Catalog>({
    key: ["alerts", "catalog"],
    read: (s) => client.catalog(s),
    initial: NO_CATALOG,
    fallbackMessage: "nie udało się wczytać tego, z czego składa się reguła",
    enabled: state.status === "ready" && present,
  });

  const refresh = () => {
    state.reload();
    rules.reload();
    catalog.reload();
  };

  if (state.status === "ready" && !present) {
    return (
      <section className="flex h-full min-h-0 flex-col gap-3 p-4">
        <h1 className="text-base font-semibold text-ink">Alerty</h1>
        <p className="text-sm text-ink-muted">
          Ten workbench nie ma pakietu alertów: <code>ALERTS_DATABASE_URL</code> nie jest ustawione, więc pakiet nie jest częścią
          procesu. To działająca konfiguracja, nie awaria — nikt nikogo o niczym nie powiadamia.
        </p>
      </section>
    );
  }

  const found = state.value.state;
  const notes = state.status === "ready" ? warnings(found) : [];
  const ready = catalog.status === "ready";

  async function propose(): Promise<void> {
    setFailure(null);
    setUnreadable(null);
    setDrafting(true);
    try {
      const draft = await client.draft(sentence.trim(), signal());
      if (draft.rule === null) {
        setUnreadable({ understood: draft.understood, defects: draft.defects });
        return;
      }
      setDialog({
        kind: "rule",
        start: { form: formFrom(draft.rule, catalog.value), defects: draft.defects, understood: draft.understood, notes: draft.notes },
      });
    } catch (cause: unknown) {
      setFailure(messageOf(cause, "nie udało się zaproponować reguły"));
    } finally {
      setDrafting(false);
    }
  }

  async function act(work: () => Promise<unknown>, fallback: string): Promise<void> {
    setFailure(null);
    try {
      await work();
      refresh();
    } catch (cause: unknown) {
      setFailure(messageOf(cause, fallback));
    }
  }

  return (
    <section className="flex h-full min-h-0 flex-col gap-4 overflow-y-auto p-4">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-base font-semibold text-ink">Alerty</h1>
        <Button size="xs" tone="primary" disabled={!ready} onClick={() => setDialog({ kind: "rule", start: { form: blankForm(catalog.value), defects: [] } })}>
          Nowa reguła…
        </Button>
        <span className="text-xs text-ink-faint">
          {found.rulesEnabled} włączonych · {found.rulesDisabled} wyłączonych
          {found.rulesWithDefects > 0 && ` · ${found.rulesWithDefects} z wadą`}
          {found.waitingFires > 0 && ` · ${found.waitingFires} czeka na wysłanie`}
        </span>
      </header>

      {state.error !== null && <UnreachableNotice onRetry={state.reload}>{state.error}</UnreachableNotice>}
      {notes.map((note) => (
        <p key={note} className="rounded bg-warning-soft px-3 py-1 text-sm font-semibold text-warning">
          {note}
        </p>
      ))}
      {failure !== null && (
        <p role="alert" className="text-sm text-critical">
          {failure}
        </p>
      )}

      <div className="flex flex-col gap-2">
        <label htmlFor="alert-sentence" className="text-xs text-ink-secondary">
          Albo opisz zdaniem — dostaniesz formularz do sprawdzenia, nic nie zostanie zapisane samo
        </label>
        <div className="flex gap-2">
          <textarea
            id="alert-sentence"
            className="min-w-0 flex-1 rounded border border-border bg-sunken px-2 py-1 text-sm text-ink"
            rows={2}
            placeholder="np. daj znać, gdy EURUSD przebije 1,10 w górę, nie częściej niż raz na godzinę"
            value={sentence}
            disabled={!catalog.value.drafting}
            onChange={(e) => setSentence(e.target.value)}
          />
          <Button size="sm" disabled={!catalog.value.drafting || drafting || sentence.trim().length < 3 || !ready} onClick={() => void propose()}>
            {drafting ? "Czytam…" : "Zaproponuj regułę"}
          </Button>
        </div>
        {ready && !catalog.value.drafting && (
          <p className="text-xs text-ink-faint">
            Pisanie zdaniem jest wyłączone: <code>ALERTS_OPENAI_API_KEY</code> nie jest ustawione. Formularz działa bez niego.
          </p>
        )}
        {unreadable && (
          <div role="alert" className="text-xs text-critical">
            {unreadable.understood && <p>Zrozumiałem to tak: {unreadable.understood}</p>}
            {unreadable.defects.map((one) => (
              <p key={one.message}>{one.message}</p>
            ))}
          </div>
        )}
      </div>

      {rules.error !== null && <UnreachableNotice onRetry={rules.reload}>{rules.error}</UnreachableNotice>}
      {catalog.error !== null && <UnreachableNotice onRetry={catalog.reload}>{catalog.error}</UnreachableNotice>}

      <ul className="flex flex-col gap-2">
        {rules.value.length === 0 && rules.status === "ready" && (
          <li className="text-sm text-ink-faint">Nie ma żadnej reguły — nikogo o niczym się nie powiadamia.</li>
        )}
        {rules.value.map((rule) => {
          const status = statusOf(rule);
          return (
            <li key={rule.id} className="flex flex-col gap-1 rounded border border-border/60 bg-sunken/40 px-3 py-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-ink">{rule.name}</span>
                <span className={`text-xs ${TONE[status.tone]}`}>{status.label}</span>
                <span className="ml-auto flex gap-1">
                  <Button size="2xs" tone="muted" aria-expanded={open === rule.id} onClick={() => setOpen(open === rule.id ? null : rule.id)}>
                    Historia
                  </Button>
                  <Button
                    size="2xs"
                    tone="muted"
                    disabled={!ready}
                    onClick={() => setDialog({ kind: "rule", start: { form: formFrom(rule, catalog.value), defects: rule.defects }, editing: rule })}
                  >
                    Edytuj…
                  </Button>
                  <Button
                    size="2xs"
                    tone="muted"
                    onClick={() => void act(() => client.setEnabled(rule.id, !rule.enabled, signal()), "nie udało się przełączyć reguły")}
                  >
                    {rule.enabled ? "Wyłącz" : "Włącz"}
                  </Button>
                  <Button size="2xs" tone="critical" onClick={() => setDialog({ kind: "delete", rule })}>
                    Usuń…
                  </Button>
                </span>
              </div>
              <p className="text-xs text-ink-secondary">{describeSource(rule.source)}</p>
              <p className="text-xs text-ink-faint">
                → {rule.destination}
                {rule.lastFiredAt && ` · ostatnio odpaliła ${rule.lastFiredAt.toLocaleString("pl-PL")}`}
              </p>
              {rule.defects.map((one) => (
                <p key={one.message} className="text-xs text-critical">
                  {one.message}
                </p>
              ))}
              {open === rule.id && <HistoryPanel api={client} rule={rule} />}
            </li>
          );
        })}
      </ul>

      {dialog?.kind === "rule" && (
        <RuleDialog
          api={client}
          catalog={catalog.value}
          start={dialog.start}
          editing={dialog.editing}
          onClose={() => setDialog(null)}
          onDone={refresh}
        />
      )}
      {dialog?.kind === "delete" && (
        <DeleteRuleDialog api={client} rule={dialog.rule} onClose={() => setDialog(null)} onDone={refresh} />
      )}
    </section>
  );
}

function HistoryPanel({ api, rule }: { api: AlertsApi; rule: Rule }) {
  const history = useRead<History>({
    key: ["alerts", "history", rule.id],
    read: (s) => api.history(rule.id, s),
    initial: { fires: [], checks: [] },
    fallbackMessage: "nie udało się wczytać historii reguły",
  });
  if (history.error !== null) return <UnreachableNotice onRetry={history.reload}>{history.error}</UnreachableNotice>;
  const { fires, checks } = history.value;
  if (history.status === "ready" && fires.length === 0 && checks.length === 0) {
    return <p className="text-xs text-ink-faint">Ta reguła jeszcze nic nie zrobiła.</p>;
  }
  return (
    <div className="flex flex-col gap-1 border-t border-border/40 pt-1 text-xs">
      {fires.map((one) => (
        <p key={`f${one.at.toISOString()}${one.text}`} className="text-ink-secondary">
          {one.at.toLocaleString("pl-PL")} — {FIRE_LABEL[one.state]}
          {one.reason ? ` (${one.reason})` : ""}: {one.text.split("\n")[0]}
        </p>
      ))}
      {checks.map((one) => (
        <p key={`c${one.at.toISOString()}${one.reason}`} className="text-ink-faint">
          {one.at.toLocaleString("pl-PL")} — {CHECK_LABEL[one.outcome]}: {one.reason}
        </p>
      ))}
    </div>
  );
}
