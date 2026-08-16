import type { TeamTradingLimits } from "./teamsApi";

/**
 * The team's own settings, beside the agents rather than behind a dialog — the same
 * view the operator composes the team in (`terminal-teams`, "Granice handlowe ustawia
 * się w tym samym widoku co resztę zespołu").
 *
 * **Every field starts and stays empty unless the operator types in it, and empty means
 * no limit.** Nothing here suggests a number, and nothing fills one in on save: a
 * ceiling the operator did not choose, wearing the look of one they did, is worse than
 * no ceiling at all (`teams-trading`, "Każda granica handlowa daje się wyłączyć, a moduł
 * żadnej nie narzuca"). A team told to trade with everything it has is an experiment the
 * operator is entitled to run; what stops an irreversible mistake is the demo account
 * `trading-mcp` refuses to start without, not a number in this panel.
 */
export function TeamLimitsPanel({
  trading,
  onChange,
}: {
  trading: TeamTradingLimits;
  onChange(patch: Partial<TeamTradingLimits>): void;
}) {
  const unlimited =
    trading.maxOrderSize === null &&
    trading.ordersPerRun === null &&
    trading.ordersPerDay === null;

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-auto border-l border-border p-3">
      <div>
        <h3 className="text-sm text-ink">Team</h3>
        <p className="text-xs text-ink-muted">
          Pick an agent to edit it, or drag from one agent's right edge to another's left
          to make it wait for that one.
        </p>
      </div>

      <fieldset className="flex flex-col gap-2">
        <legend className="text-xs uppercase tracking-wide text-ink-faint">
          Trading limits
        </legend>
        <p className="text-xs text-ink-muted">
          Empty means no limit. These apply only to agents holding a tool that changes the
          account.
        </p>

        <NumberField
          id="max-order-size"
          label="Max order size"
          value={trading.maxOrderSize}
          onChange={(value) => onChange({ maxOrderSize: value })}
        />
        <CountField
          id="orders-per-run"
          label="Orders per run"
          value={trading.ordersPerRun}
          onChange={(value) => onChange({ ordersPerRun: value })}
        />
        <CountField
          id="orders-per-day"
          label="Orders per day"
          value={trading.ordersPerDay}
          onChange={(value) => onChange({ ordersPerDay: value })}
        />

        {unlimited && (
          <p className="text-xs text-warning" data-testid="unlimited-note">
            No trading limits set — agents with a write tool may place orders without
            bound, on the demo account.
          </p>
        )}
      </fieldset>
    </div>
  );
}

/** A decimal, kept as the string the operator typed: the module compares it, nothing
 *  here computes with it, and a round trip through a float is how a written 0.1 comes
 *  back as something else. */
function NumberField({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: string | null;
  onChange(value: string | null): void;
}) {
  return (
    <Field id={id} label={label}>
      <input
        id={id}
        inputMode="decimal"
        placeholder="no limit"
        value={value ?? ""}
        onChange={(event) => {
          const text = event.target.value.trim();
          onChange(text === "" ? null : text);
        }}
        className="w-full rounded border border-border bg-panel px-2 py-1 text-sm text-ink"
      />
    </Field>
  );
}

function CountField({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: number | null;
  onChange(value: number | null): void;
}) {
  return (
    <Field id={id} label={label}>
      <input
        id={id}
        type="number"
        min={1}
        step={1}
        placeholder="no limit"
        value={value ?? ""}
        onChange={(event) => {
          const text = event.target.value.trim();
          if (text === "") {
            onChange(null);
            return;
          }
          const parsed = Number(text);
          // A count this cannot read is left as it was rather than turned into a number
          // nobody typed. The module refuses zero and below outright, and its refusal is
          // the one the operator should see — not a silent correction here.
          if (Number.isFinite(parsed)) onChange(Math.trunc(parsed));
        }}
        className="w-full rounded border border-border bg-panel px-2 py-1 text-sm text-ink"
      />
    </Field>
  );
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
