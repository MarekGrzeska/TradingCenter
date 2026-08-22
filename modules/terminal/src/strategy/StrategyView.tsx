import { useMemo, useState } from "react";
import { resolveEndpoints } from "../data/config";
import { strategyIdentity } from "../data/marketData";
import { useRead } from "../data/query";
import { Button } from "../ui/Button";
import { UnreachableNotice } from "../ui/UnreachableNotice";
import { DecisionRow } from "./DecisionRow";
import { StartWatchDialog } from "./StartWatchDialog";
import {
  createStrategyApi,
  type Decision,
  type Strategy,
  type StrategyApi,
  type Watch,
} from "./strategyApi";

/**
 * What the strategies decided, and — far more often — why they decided nothing.
 *
 * **This screen is mostly refusals, on purpose.** A strategy worth running says no to the
 * large majority of the bars it sees, so a tab built around setups would be empty most of
 * the time and empty precisely when somebody asks the question people actually ask these
 * systems: why has nothing happened. The refusals are the answer, so they are the list,
 * and the kind of refusal is a badge rather than a detail — coverage, the strategy itself
 * and a platform limit have three different remedies (specs/terminal-strategy).
 *
 * **Nothing here reaches an account.** The module behind this screen has no route that
 * places, amends or cancels an order and will not grow one; a button suggesting otherwise
 * would be the only place in this terminal promising execution where there is none.
 *
 * The catalogue is read-only for the same kind of reason: a strategy is code in the
 * deployed image, not a row in a table, and an edit control would promise something this
 * module cannot do about the logic that decides on money.
 */

/** How often the decisions are re-asked. The platform decides on closed bars — hourly for
 *  the strategy that exists today — so anything faster is asking for the same answer. */
const POLL_MS = 60_000;

const NO_STRATEGIES: Strategy[] = [];
const NO_WATCHES: Watch[] = [];
const NO_DECISIONS: Decision[] = [];

export function StrategyView({ api }: { api?: StrategyApi } = {}) {
  const client = useMemo(
    () => api ?? createStrategyApi(resolveEndpoints().strategyHttp, strategyIdentity),
    [api],
  );

  const [starting, setStarting] = useState(false);
  const [chosen, setChosen] = useState<string | null>(null);

  const strategies = useRead<Strategy[]>({
    key: ["strategy", "catalogue"],
    read: (signal) => client.listStrategies(signal),
    initial: NO_STRATEGIES,
    fallbackMessage: "nie udało się odczytać katalogu strategii",
  });

  const watches = useRead<Watch[]>({
    key: ["strategy", "watches"],
    read: (signal) => client.listWatches(signal),
    initial: NO_WATCHES,
    fallbackMessage: "nie udało się odczytać obserwacji",
  });

  const decisions = useRead<Decision[]>({
    key: ["strategy", "decisions", chosen],
    // No `action` filter, deliberately: the refusals are what this list is for.
    read: (signal) =>
      client.listDecisions(signal, chosen === null ? undefined : { strategyId: chosen }),
    initial: NO_DECISIONS,
    fallbackMessage: "nie udało się odczytać decyzji",
    pollMs: POLL_MS,
  });

  const nothingWatched = watches.status === "ready" && watches.value.length === 0;
  const nothingDecided = decisions.status === "ready" && decisions.value.length === 0;

  async function toggle(watch: Watch) {
    await client.setWatchActive(watch.id, !watch.active, new AbortController().signal);
    watches.reload();
  }

  return (
    <section className="flex h-full min-h-0 flex-col gap-4 p-4">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-base font-semibold text-ink">Strategie</h1>
        <span className="text-xs text-ink-faint">
          decyzje z domkniętych świec · odmowy są tu treścią, nie usterką · odświeżane co{" "}
          {POLL_MS / 1000}s
        </span>
        <div className="ml-auto flex items-center gap-2">
          <Button size="xs" onClick={() => setStarting(true)}>
            Obserwuj parę
          </Button>
          <Button
            size="xs"
            tone="muted"
            onClick={() => {
              watches.reload();
              decisions.reload();
            }}
          >
            Odśwież
          </Button>
        </div>
      </header>

      {/* Two failures, told apart, because the next move differs. A refusal is a permission
          that was not granted — this module decides who reaches its REST contract and the
          platform's gate cannot — while unreachable is the module being down. */}
      {strategies.error !== null && (
        <UnreachableNotice onRetry={strategies.reload}>{strategies.error}</UnreachableNotice>
      )}
      {strategies.error === null && decisions.error !== null && (
        <UnreachableNotice onRetry={decisions.reload}>
          Decyzji nie udało się odświeżyć — {decisions.error}. Poniżej jest ostatnia
          odpowiedź, nie stan na teraz.
        </UnreachableNotice>
      )}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className={chosen === null ? "chip chip-on" : "chip"}
          onClick={() => setChosen(null)}
        >
          wszystkie
        </button>
        {strategies.value.map((strategy) => (
          <button
            key={strategy.id}
            type="button"
            className={chosen === strategy.id ? "chip chip-on" : "chip"}
            onClick={() => setChosen(strategy.id)}
            title={strategy.description}
          >
            {strategy.name}
          </button>
        ))}
      </div>

      {nothingWatched && (
        <p className="text-xs text-ink-muted" data-testid="nothing-watched">
          Żadna para nie jest obserwowana, więc nie ma czego oceniać. Wskaż strategię
          i instrument — platforma zacznie decydować na każdej domkniętej świecy i zapisze
          także każdą odmowę.
        </p>
      )}

      {watches.value.length > 0 && (
        <ul className="flex flex-wrap gap-2" data-testid="watches">
          {watches.value.map((watch) => (
            <li key={watch.id} className={watch.active ? "watch watch-on" : "watch"}>
              <span className="watch-symbol">{watch.symbol}</span>
              <span className="watch-strategy">{watch.strategyId}</span>
              <Button size="xs" tone="muted" onClick={() => void toggle(watch)}>
                {/* Stopping is not deleting, and the word has to say so: the decisions this
                    pair already produced stay readable afterwards. */}
                {watch.active ? "zatrzymaj" : "wznów"}
              </Button>
            </li>
          ))}
        </ul>
      )}

      {decisions.status === "loading" && (
        <p className="text-xs text-ink-faint">Czytam decyzje…</p>
      )}

      {nothingDecided && !nothingWatched && (
        <p className="text-xs text-ink-muted">
          Jeszcze żadnej decyzji. Pierwsza pojawi się po domknięciu świecy w rozdzielczości
          strategii.
        </p>
      )}

      {decisions.value.length > 0 && (
        <div className="min-h-0 flex-1 overflow-auto">
          <table className="decisions">
            <thead>
              <tr>
                <th>świeca</th>
                <th>instrument</th>
                <th>wynik</th>
                <th>powód</th>
                <th>wejście / obrona</th>
                <th>R</th>
              </tr>
            </thead>
            <tbody>
              {decisions.value.map((decision) => (
                <DecisionRow key={decision.id} decision={decision} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {starting && (
        <StartWatchDialog
          client={client}
          strategies={strategies.value}
          onClose={() => setStarting(false)}
          onStarted={() => {
            setStarting(false);
            watches.reload();
          }}
        />
      )}
    </section>
  );
}
