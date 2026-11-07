import type { DemoAccount } from "../accounts/accountsApi";
import type { TeamTradingLimits } from "./teamsApi";

/**
 * The team itself, always the whole right-hand column, because a ceiling nobody can find is one nobody sets.
 * An empty field is "no limit", not an omission — the module saves it and nags about nothing (specs/teams-trading).
 */
export function TeamPanel({
  trading,
  accounts,
  liveAccounts = [],
  accountsNote,
  sharedWith,
  onChange,
}: {
  trading: TeamTradingLimits;
  /** What the gateway lists; the choice is never typed in. */
  accounts: DemoAccount[];
  /** What the live account's gateway lists — one account, or none when the terminal has no address for it. */
  liveAccounts?: DemoAccount[];
  /** Why the list is empty, when it is — a failed read, rather than an account-less login. */
  accountsNote: string | null;
  /** Names of the other teams whose latest revision trades on the chosen account. */
  sharedWith: string[];
  onChange(patch: Partial<TeamTradingLimits>, kind: string): void;
}) {
  const live = trading.environment === "live";
  const listed = live ? liveAccounts : accounts;
  const chosen = trading.accountId ?? "";
  // A revision can name an account the gateway no longer lists; kept as an option so the select does not lie.
  const unlisted = chosen !== "" && !listed.some((account) => account.id === chosen);

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

        <Field id="trading-environment" label="Environment">
          <select
            id="trading-environment"
            value={live ? "live" : "demo"}
            onChange={(event) =>
              onChange(
                // The account belongs to the environment it was chosen in; switching drops it.
                { environment: event.target.value === "live" ? "live" : "demo", accountId: null },
                "select:trading:environment",
              )
            }
            className="w-full rounded border border-border bg-panel px-2 py-1 text-sm text-ink"
          >
            <option value="demo">demo</option>
            <option value="live">live account — real money</option>
          </select>
        </Field>
        {live && (
          <p className="text-xs font-semibold text-critical">
            This team trades real money. The live gateway holds every order to its limits; the
            account below is required.
          </p>
        )}

        <Field id="trading-account" label="Account">
          <select
            id="trading-account"
            value={chosen}
            onChange={(event) =>
              onChange(
                { accountId: event.target.value === "" ? null : event.target.value },
                "select:trading:accountId",
              )
            }
            className="w-full rounded border border-border bg-panel px-2 py-1 text-sm text-ink"
          >
            <option value="">{live ? "choose the live account" : "the active account"}</option>
            {listed.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name} · {account.currency} {account.balance.toFixed(2)}
              </option>
            ))}
            {unlisted && <option value={chosen}>{chosen} (not listed by the gateway)</option>}
          </select>
        </Field>
        {accountsNote !== null && <p className="text-xs text-critical">{accountsNote}</p>}
        {sharedWith.length > 0 && (
          <p className="text-xs text-warning">
            Also traded by {sharedWith.join(", ")} — their results will mix in one balance.
          </p>
        )}
        <p className="text-xs text-ink-faint">
          A team on its own account keeps it whatever the active account is, and may not carry
          the tools that switch or fund one.
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
