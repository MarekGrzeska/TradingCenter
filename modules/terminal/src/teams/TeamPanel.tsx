import type { TeamTradingLimits } from "./teamsApi";

/**
 * The team itself, always the whole right-hand column, because a ceiling nobody can find is one nobody sets.
 * An empty field is "no limit", not an omission — the module saves it and nags about nothing (specs/teams-trading).
 */
export function TeamPanel({
  trading,
  onChange,
}: {
  trading: TeamTradingLimits;
  onChange(patch: Partial<TeamTradingLimits>, kind: string): void;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-auto border-l border-border p-3">
      <p className="text-xs text-ink-muted">
        Open an agent with the gear on its box, or drag from one agent's right edge to
        another's left to make it wait for that one.
      </p>

      <fieldset className="flex flex-col gap-3">
        <legend className="text-xs uppercase tracking-wide text-ink-faint">Trading limits</legend>
        <p className="text-xs text-ink-muted">
          Left empty, a limit is no limit. They bind every agent carrying a tool that moves
          the account.
        </p>

        <Field id="trading-max-size" label="Largest order size">
          <input
            id="trading-max-size"
            inputMode="decimal"
            placeholder="no limit"
            // The string as typed, never a parsed number: it is compared against the size an agent asks
            // for, and a round trip through a float is where a size stops being the one written down.
            value={trading.maxOrderSize ?? ""}
            onChange={(event) =>
              onChange(
                { maxOrderSize: emptyToNull(event.target.value) },
                "text:trading:maxOrderSize",
              )
            }
            className="w-full rounded border border-border bg-panel px-2 py-1 text-sm text-ink"
          />
        </Field>

        <Field id="trading-per-run" label="Orders per run">
          <input
            id="trading-per-run"
            type="number"
            min={1}
            placeholder="no limit"
            value={trading.ordersPerRun ?? ""}
            onChange={(event) =>
              onChange(
                { ordersPerRun: countOrNull(event.target.value) },
                "text:trading:ordersPerRun",
              )
            }
            className="w-full rounded border border-border bg-panel px-2 py-1 text-sm text-ink"
          />
        </Field>

        <Field id="trading-per-day" label="Orders per day">
          <input
            id="trading-per-day"
            type="number"
            min={1}
            placeholder="no limit"
            value={trading.ordersPerDay ?? ""}
            onChange={(event) =>
              onChange(
                { ordersPerDay: countOrNull(event.target.value) },
                "text:trading:ordersPerDay",
              )
            }
            className="w-full rounded border border-border bg-panel px-2 py-1 text-sm text-ink"
          />
        </Field>
        <p className="text-xs text-ink-faint">
          A run that reaches its per-run count stops and says so; an order over the size
          limit comes back to the agent as a refused call and the run goes on. The daily
          count is checked before a run starts at all.
        </p>
      </fieldset>
    </div>
  );
}

function emptyToNull(value: string): string | null {
  return value.trim() === "" ? null : value.trim();
}

/** A count, or no limit. A number this cannot read is left as no limit rather than as a
 *  zero — the module refuses zero, and inventing one here would refuse a save the operator
 *  never asked for. */
function countOrNull(value: string): number | null {
  const parsed = Number(value.trim());
  return value.trim() === "" || !Number.isFinite(parsed) ? null : parsed;
}

function Field({
  id,
  label,
  children,
}: {
  id: string;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-xs uppercase tracking-wide text-ink-faint">
        {label}
      </label>
      {children}
    </div>
  );
}
