import { useMemo, useState } from "react";
import { ConfirmDialog } from "../ui/ConfirmDialog";
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
 */
export function StartWatchDialog({
  client,
  strategies,
  onClose,
  onStarted,
}: {
  client: StrategyApi;
  strategies: Strategy[];
  onClose(): void;
  onStarted(): void;
}) {
  const [strategyId, setStrategyId] = useState(strategies[0]?.id ?? "");
  const [symbol, setSymbol] = useState("");
  const [overrides, setOverrides] = useState<Record<string, string>>({});

  const strategy = useMemo(
    () => strategies.find((entry) => entry.id === strategyId) ?? null,
    [strategies, strategyId],
  );

  return (
    <ConfirmDialog
      title="Obserwuj parę"
      confirmLabel="Zacznij"
      busyLabel="Pytam moduł…"
      confirmDisabled={strategyId === "" || symbol.trim() === ""}
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
          symbol.trim(),
          new AbortController().signal,
          Object.keys(params).length === 0 ? undefined : params,
        );
        onStarted();
      }}
      onClose={onClose}
    >
      <div className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-ink-secondary">Strategia</span>
          <select
            className="rounded border border-border bg-sunken px-2 py-1 text-ink"
            value={strategyId}
            onChange={(e) => {
              setStrategyId(e.target.value);
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
              {strategy.description} · decyduje na świecach {strategy.resolution}
            </span>
          )}
        </label>

        <label className="flex flex-col gap-1 text-xs">
          <span className="text-ink-secondary">Instrument</span>
          <input
            className="rounded border border-border bg-sunken px-2 py-1 text-ink"
            value={symbol}
            autoFocus
            placeholder="US100"
            onChange={(e) => setSymbol(e.target.value)}
          />
          <span className="text-ink-faint">
            Ten sam symbol, którym nazywa go archiwum świec.
          </span>
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
