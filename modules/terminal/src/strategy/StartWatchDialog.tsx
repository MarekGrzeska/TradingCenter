import { useMemo, useState } from "react";
import { useRead } from "../data/query";
import { RESOLUTIONS, type TrackedPair } from "../data/types";
import type { ArchiveAdmin } from "../data/source";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { RESOLUTION_LABEL } from "../ui/resolutionLabel";
import type { Strategy, StrategyApi } from "./strategyApi";

/**
 * Starting to watch a pair with a strategy.
 *
 * **The ranges come from the module, not from here.** Every parameter carries its own
 * bounds in the catalogue, and the module refuses a value outside them at the moment the
 * set is written — before any bar is evaluated. This dialog shows those bounds and lets
 * the refusal happen rather than second-guessing it: a copy of the rule here would be a
 * second opinion about numbers this screen does not own, and the two would drift.
 *
 * Left untouched, the parameters are not sent at all. The module then writes a set from
 * the strategy's own defaults, resolved — which is what would be stored either way, and is
 * one fewer place holding an opinion about values it did not declare.
 *
 * **The instrument is chosen from the archive, not typed.** A strategy decides on the
 * archive's candles and on nothing else, so a symbol it does not collect is a watch that
 * can only ever record refusals — and typed by hand, the way it is spelled is a guess the
 * operator has no way to check from here. The list is read when this dialog opens rather
 * than with the screen: it is one request, and it is only ever wanted by somebody about to
 * start something.
 */

const NO_PAIRS: TrackedPair[] = [];

/** The archive's spelling of an interval never reaches the screen (`terminal-shell` spec,
 *  "Interwały nazywają się jednakowo w całym terminalu"), and the strategy platform names
 *  them with the same words the archive does. An interval this terminal has no name for is
 *  shown as it came, which is still better than nothing. */
function intervalLabel(resolution: string): string {
  return RESOLUTION_LABEL[resolution as keyof typeof RESOLUTION_LABEL] ?? resolution;
}

export function StartWatchDialog({
  client,
  admin,
  strategies,
  onClose,
  onStarted,
}: {
  client: StrategyApi;
  admin: ArchiveAdmin;
  strategies: Strategy[];
  onClose(): void;
  onStarted(): void;
}) {
  // **Which strategy is chosen is derived, not stored until it is chosen.** The catalogue
  // can arrive after this dialog does — against a cold module in Azure that read takes
  // seconds — and an initial state captured in that window stayed empty for good: the
  // select filled itself, nothing in it was selected, and "Zacznij" was disabled with
  // nothing on screen saying why. `null` here means "not chosen yet", which resolves to
  // the first entry of whatever the catalogue turned out to hold.
  const [chosen, setChosen] = useState<string | null>(null);
  const [chosenSymbol, setChosenSymbol] = useState<string | null>(null);
  const [overrides, setOverrides] = useState<Record<string, string>>({});

  const pairs = useRead<TrackedPair[]>({
    key: ["archive", "pairs"],
    read: (signal) => admin.listPairs(signal),
    initial: NO_PAIRS,
    fallbackMessage: "nie udało się odczytać listy instrumentów",
  });

  // One entry per instrument, not per pair: the archive collects (symbol, interval) and a
  // strategy watches the instrument, deciding on the interval it declares itself.
  const symbols = useMemo(
    () => [...new Set(pairs.value.map((pair) => pair.symbol))].sort((a, b) => a.localeCompare(b)),
    [pairs.value],
  );

  const strategyId = chosen ?? strategies[0]?.id ?? "";
  const symbol = chosenSymbol ?? symbols[0] ?? "";

  const strategy = useMemo(
    () => strategies.find((entry) => entry.id === strategyId) ?? null,
    [strategies, strategyId],
  );

  // What the archive actually holds for the chosen instrument, in the terminal's own
  // interval order. Shown rather than checked against the strategy's own interval: which
  // intervals can be served from which — a rollup is built off the minute series — is the
  // archive's rule, and a copy of it here would be a second opinion that drifts. The
  // platform records a coverage refusal, with its reason, if the bars are not there.
  const held = useMemo(
    () =>
      RESOLUTIONS.filter((resolution) =>
        pairs.value.some((pair) => pair.symbol === symbol && pair.resolution === resolution),
      ).map(intervalLabel),
    [pairs.value, symbol],
  );

  return (
    <ConfirmDialog
      title="Obserwuj parę"
      confirmLabel="Zacznij"
      busyLabel="Pytam moduł…"
      confirmDisabled={strategyId === "" || symbol === ""}
      fallbackError="nie udało się założyć obserwacji"
      onConfirm={async () => {
        // Only what the operator actually typed. An untouched field means "the default",
        // and sending the default back would make this screen the author of a value it
        // merely displayed.
        const params: Record<string, number> = {};
        for (const [name, raw] of Object.entries(overrides)) {
          if (raw.trim() === "") continue;
          params[name] = Number(raw);
        }
        await client.startWatch(
          strategyId,
          symbol,
          new AbortController().signal,
          Object.keys(params).length === 0 ? undefined : params,
        );
        onStarted();
      }}
      onClose={onClose}
    >
      <div className="flex flex-col gap-3">
        {/* Both controls carry the word beside them as their own name too: the label wraps
            the hints under each of them, and a hint is not a name. */}
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-ink-secondary">Strategia</span>
          <select
            className="rounded border border-border bg-sunken px-2 py-1 text-ink"
            aria-label="Strategia"
            value={strategyId}
            disabled={strategies.length === 0}
            onChange={(e) => {
              setChosen(e.target.value);
              setOverrides({});
            }}
          >
            {strategies.map((entry) => (
              <option key={entry.id} value={entry.id}>
                {entry.name}
              </option>
            ))}
          </select>
          {strategy !== null && (
            <span className="text-ink-faint">
              {strategy.description} · decyduje na świecach {intervalLabel(strategy.resolution)}
            </span>
          )}
          {/* Said rather than left to a dead button: an empty catalogue is the one reason
              this dialog cannot start anything, and it is not the operator's doing. */}
          {strategies.length === 0 && (
            <span className="text-warning">
              Katalog strategii jeszcze nie odpowiedział — dopóki nie odpowie, nie ma czego
              zacząć. Zamknij to okno i spróbuj ponownie za chwilę.
            </span>
          )}
        </label>

        <label className="flex flex-col gap-1 text-xs">
          <span className="text-ink-secondary">Instrument</span>
          <select
            className="rounded border border-border bg-sunken px-2 py-1 text-ink"
            aria-label="Instrument"
            value={symbol}
            autoFocus
            disabled={symbols.length === 0}
            onChange={(e) => setChosenSymbol(e.target.value)}
          >
            {symbols.map((entry) => (
              <option key={entry} value={entry}>
                {entry}
              </option>
            ))}
          </select>
          {held.length > 0 && (
            <span className="text-ink-faint">
              Archiwum trzyma dla niego: {held.join(", ")}.
            </span>
          )}
          {/* Three different states behind one empty list, and the operator's next move is
              different in each: wait, sign in again or go and add an instrument. */}
          {pairs.status === "loading" && (
            <span className="text-ink-faint">Czytam listę instrumentów…</span>
          )}
          {pairs.error !== null && <span className="text-warning">{pairs.error}</span>}
          {pairs.status === "ready" && symbols.length === 0 && (
            <span className="text-warning">
              Archiwum nie zbiera żadnego instrumentu. Dodaj go w zakładce Instrumenty —
              strategia decyduje na jego świecach i na niczym innym.
            </span>
          )}
        </label>

        {strategy !== null && strategy.params.length > 0 && (
          <fieldset className="flex flex-col gap-2 text-xs">
            <legend className="text-ink-secondary">Parametry</legend>
            {strategy.params.map((param) => (
              <label key={param.name} className="flex items-center gap-2">
                <span className="w-40 text-ink-secondary">{param.name}</span>
                <input
                  className="w-24 rounded border border-border bg-sunken px-2 py-1 text-ink"
                  type="number"
                  value={overrides[param.name] ?? ""}
                  placeholder={String(param.default)}
                  onChange={(e) =>
                    setOverrides((current) => ({ ...current, [param.name]: e.target.value }))
                  }
                />
                <span className="text-ink-faint">
                  {param.min}–{param.max}
                </span>
              </label>
            ))}
            <span className="text-ink-faint">
              Puste pole znaczy „domyślna". Wartość spoza zakresu odrzuca moduł, nazywając
              parametr — zanim oceni pierwszą świecę.
            </span>
          </fieldset>
        )}

        <p className="text-xs text-ink-faint">
          Platforma zacznie decydować na każdej domkniętej świecy i zapisze także każdą
          odmowę wraz z powodem. Nie składa zleceń — setup jest odczytem.
        </p>
      </div>
    </ConfirmDialog>
  );
}
