import { useEffect, useState } from "react";
import { messageOf } from "../data/query";
import { Button } from "../ui/Button";
import { todayInWarsaw, warsawMidnightEpochSeconds } from "../ui/formatTime";
import { barsIn, interval, num, sourceLabel } from "./present";
import { costsOf, EMPTY_COSTS, fieldsOf, sameFields, type CostFields } from "./costFields";
import { Refused, type CostProfile, type Problem, type StrategiesApi } from "./strategiesApi";

const signal = () => new AbortController().signal;

interface ParamDecl {
  default: number;
  min: number;
  max: number;
  step: number;
}

function monthsBefore(day: string, months: number): string {
  const [y, m, d] = day.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1 - months, d));
  return date.toISOString().slice(0, 10);
}

type ProfileState = { status: "loading" } | { status: "ready"; profile: CostProfile } | { status: "failed" };

/**
 * A run of one revision: its range in Polish days, its parameters inside their declared ranges, and costs filled from the
 * instrument's profile — read off capital.com when there is none, changed here for this run alone, or left out on purpose
 * with "bez kosztów". The profile is changed with its own buttons (`terminal-strategies`).
 */
export function RunForm({
  api,
  strategyId,
  revision,
  symbol,
  params,
  execution,
  maxExecutionBars,
  onQueued,
}: {
  api: StrategiesApi;
  strategyId: number;
  revision: number;
  symbol: string;
  params: Record<string, ParamDecl>;
  execution: string;
  maxExecutionBars: number | null;
  onQueued(runId: number): void;
}) {
  const today = todayInWarsaw();
  const [from, setFrom] = useState(monthsBefore(today, 12));
  const [to, setTo] = useState(today);
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(Object.entries(params).map(([name, p]) => [name, String(p.default)])),
  );
  const [costs, setCosts] = useState<CostFields>(EMPTY_COSTS);
  const [profile, setProfile] = useState<ProfileState>({ status: "loading" });
  const [withoutCosts, setWithoutCosts] = useState(false);
  const [capital, setCapital] = useState("10000");
  const [seed, setSeed] = useState("1");
  const [problems, setProblems] = useState<Problem[]>([]);
  const [failure, setFailure] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function show(found: CostProfile): void {
    setProfile({ status: "ready", profile: found });
    setCosts(fieldsOf(found.costs));
  }

  // An instrument without a profile gets the broker's, with no step of the operator's.
  useEffect(() => {
    let live = true;
    setProfile({ status: "loading" });
    void (async () => {
      try {
        const found = (await api.costs(symbol, signal())) ?? (await api.costsFromBroker(symbol, signal()));
        if (live) show(found);
      } catch (cause: unknown) {
        if (!live) return;
        setProfile({ status: "failed" });
        setCosts(EMPTY_COSTS);
        setFailure(messageOf(cause, "nie udało się pobrać kosztów z capital.com — wpisz je albo spróbuj odświeżyć"));
      }
    })();
    return () => {
      live = false;
    };
  }, [api, symbol]);

  const edited = profile.status !== "ready" || !sameFields(costs, fieldsOf(profile.profile.costs));

  const start = new Date(warsawMidnightEpochSeconds(from) * 1000);
  const end = new Date(warsawMidnightEpochSeconds(to) * 1000);
  const bars = barsIn(start, end, execution);
  const overCeiling = maxExecutionBars !== null && bars > maxExecutionBars;
  const problemAt = (path: string) => problems.filter((p) => p.path === path || p.path.startsWith(`${path}.`));

  async function queue(): Promise<void> {
    setBusy(true);
    setFailure(null);
    setProblems([]);
    try {
      const id = await api.enqueue(
        {
          strategyId,
          revision,
          from: start,
          to: end,
          params: Object.fromEntries(Object.entries(values).map(([k, v]) => [k, Number(v)])),
          // Unchanged, the package takes them from the profile itself and records where they came from.
          costs: withoutCosts || !edited ? null : costsOf(costs),
          withoutCosts,
          capital: Number(capital),
          seed: Number(seed),
        },
        signal(),
      );
      onQueued(id);
    } catch (cause: unknown) {
      if (cause instanceof Refused) setProblems(cause.problems);
      setFailure(messageOf(cause, "nie udało się zakolejkować uruchomienia"));
    } finally {
      setBusy(false);
    }
  }

  async function saveProfile(): Promise<void> {
    setFailure(null);
    setSaved(null);
    try {
      show(await api.putCosts(symbol, costsOf(costs), signal()));
      setSaved(`Zapisano jako profil kosztów ${symbol}.`);
    } catch (cause: unknown) {
      setFailure(messageOf(cause, "nie udało się zapisać profilu kosztów"));
    }
  }

  async function refreshFromBroker(): Promise<void> {
    setFailure(null);
    setSaved(null);
    try {
      show(await api.costsFromBroker(symbol, signal()));
      setSaved(`Profil kosztów ${symbol} pobrany z capital.com.`);
    } catch (cause: unknown) {
      setFailure(messageOf(cause, "nie udało się pobrać kosztów z capital.com; profil został bez zmian"));
    }
  }

  const input = "rounded border border-border bg-sunken px-2 py-1 text-sm text-ink";
  const costField = (key: keyof CostFields, label: string, hint?: string) => (
    <label className="flex flex-col gap-1 text-xs text-ink-secondary">
      {label}
      <input
        className={input}
        value={costs[key]}
        disabled={withoutCosts}
        onChange={(e) => setCosts({ ...costs, [key]: e.target.value })}
      />
      {hint && <span className="text-ink-faint">{hint}</span>}
    </label>
  );

  return (
    <form
      aria-label="Uruchomienie"
      className="flex flex-col gap-3 rounded border border-border bg-panel p-3"
      onSubmit={(e) => {
        e.preventDefault();
        void queue();
      }}
    >
      <h3 className="text-sm font-semibold text-ink">Backtest rewizji {revision}</h3>
      <div className="flex flex-wrap gap-3">
        <label className="flex flex-col gap-1 text-xs text-ink-secondary">
          Od (dzień, czas polski)
          <input type="date" className={input} value={from} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1 text-xs text-ink-secondary">
          Do (bez tego dnia)
          <input type="date" className={input} value={to} onChange={(e) => setTo(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1 text-xs text-ink-secondary">
          Kapitał
          <input className={input} value={capital} onChange={(e) => setCapital(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1 text-xs text-ink-secondary">
          Ziarno
          <input className={input} value={seed} onChange={(e) => setSeed(e.target.value)} />
        </label>
      </div>
      <p className={`text-xs ${overCeiling ? "text-critical" : "text-ink-faint"}`}>
        Zakres obejmuje {num(bars)} świec {interval(execution)}, na których wykonuje się ta strategia
        {maxExecutionBars !== null && <>, z {num(maxExecutionBars)}, które przyjmuje jedno uruchomienie</>}
        {overCeiling && " — skróć zakres albo podziel go na kilka uruchomień"}.
      </p>
      {problemAt("to").map((p) => (
        <p key={p.message} className="text-xs text-critical">{p.message}</p>
      ))}

      {Object.keys(params).length > 0 && (
        <fieldset className="flex flex-wrap gap-3">
          <legend className="text-xs font-semibold text-ink-muted">Parametry</legend>
          {Object.entries(params).map(([name, p]) => (
            <label key={name} className="flex flex-col gap-1 text-xs text-ink-secondary">
              p.{name} ({num(p.min)}–{num(p.max)})
              <input
                className={input}
                type="number"
                min={p.min}
                max={p.max}
                step={p.step}
                value={values[name] ?? ""}
                onChange={(e) => setValues({ ...values, [name]: e.target.value })}
              />
              {problemAt(`params.${name}`).map((problem) => (
                <span key={problem.message} className="text-critical">{problem.message}</span>
              ))}
            </label>
          ))}
        </fieldset>
      )}

      <fieldset className="flex flex-wrap items-end gap-3">
        <legend className="text-xs font-semibold text-ink-muted">
          Koszty {symbol}
          {profile.status === "loading" && " — pobieram z capital.com…"}
          {profile.status === "ready" && ` — ${sourceLabel(profile.profile)}`}
          {profile.status === "ready" && edited && "; zmiana tutaj dotyczy tylko tego uruchomienia"}
          {profile.status === "failed" && " — capital.com nie podał kosztów; wpisz je albo odśwież"}
        </legend>
        {costField("spread", "Spread", "jedna wartość albo 24, po jednej na godzinę UTC")}
        {costField("slippage", "Poślizg na stronę")}
        {costField("overnightLong", "Finansowanie long / noc")}
        {costField("overnightShort", "Finansowanie short / noc")}
        {costField("rolloverHour", "Godzina rozliczenia (UTC)")}
        <Button type="button" size="xs" disabled={withoutCosts} onClick={() => void saveProfile()}>
          Zapisz jako profil {symbol}
        </Button>
        <Button type="button" size="xs" tone="muted" disabled={withoutCosts} onClick={() => void refreshFromBroker()}>
          Odśwież z capital.com
        </Button>
      </fieldset>
      <label className="flex items-center gap-2 text-xs text-ink-secondary">
        <input type="checkbox" checked={withoutCosts} onChange={(e) => setWithoutCosts(e.target.checked)} />
        Bez kosztów
      </label>
      {withoutCosts && (
        <p className="text-xs text-warning">
          Wynik pominie spread, poślizg i finansowanie, więc będzie nierealistyczny. Raport i lista uruchomień to oznaczą.
        </p>
      )}
      {problemAt("costs").map((p) => (
        <p key={p.path + p.message} className="text-xs text-critical">{p.path}: {p.message}</p>
      ))}
      {saved !== null && <p className="text-xs text-ink-secondary">{saved}</p>}
      {failure !== null && (
        <p role="alert" className="text-sm text-critical">
          {failure}
        </p>
      )}
      <div>
        <Button type="submit" tone="primary" disabled={busy || overCeiling || (!withoutCosts && profile.status === "loading")}>
          Uruchom backtest
        </Button>
      </div>
    </form>
  );
}
