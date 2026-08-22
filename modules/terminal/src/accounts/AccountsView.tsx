import { useCallback, useMemo, useState } from "react";
import { createAccountsApi, type AccountsApi, type DemoAccount } from "./accountsApi";
import { gatewayIdentity } from "../data/marketData";
import { resolveEndpoints } from "../data/config";
import { useRead } from "../data/query";
import { Button } from "../ui/Button";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { UnreachableNotice } from "../ui/UnreachableNotice";

/**
 * The demo accounts, and the money on them.
 *
 * What the operator had before this tab was a sentence from the agent, on request. What is
 * here is the standing background of trading: which accounts exist, what is on them, what
 * is open on the one being traded, and a way to add or take demo money without leaving the
 * terminal (`terminal-accounts` spec).
 *
 * **Positions belong to the active account only**, and that is the provider's shape rather
 * than a shortcut: capital.com ties open positions to the session, and a session has one
 * account. Reading another account's positions would mean switching to it — which ends the
 * quote stream the archive collects candles through, and changes where the next order
 * goes. The screen says so before it does it, and never does it to satisfy a read.
 */

/** How often the screen re-asks. The provider counts ten requests a second **per account**
 *  against everything this system does — the archive filling candles, the agent's tools,
 *  this screen — so a tab refreshing twice a second would be taking that budget from the
 *  work. Five seconds is faster than an operator can act on and cheap enough to ignore. */
const POLL_MS = 5000;

export function AccountsView({ api }: { api?: AccountsApi } = {}) {
  const client = useMemo(
    () => api ?? createAccountsApi(resolveEndpoints().gatewayHttp, gatewayIdentity),
    [api],
  );

  const accounts = useRead<DemoAccount[]>({
    key: ["gateway", "accounts"],
    read: (signal) => client.listAccounts(signal),
    initial: EMPTY_ACCOUNTS,
    fallbackMessage: "could not read the accounts",
    pollMs: POLL_MS,
  });

  const positions = useRead({
    key: ["gateway", "positions"],
    read: (signal) => client.listPositions(signal),
    initial: EMPTY_POSITIONS,
    fallbackMessage: "could not read the open positions",
    pollMs: POLL_MS,
  });

  const active = accounts.value.find((account) => account.active) ?? null;
  const [pendingSwitch, setPendingSwitch] = useState<DemoAccount | null>(null);
  const [toppingUp, setToppingUp] = useState(false);

  const reloadBoth = useCallback(() => {
    accounts.reload();
    positions.reload();
  }, [accounts, positions]);

  return (
    <section className="flex h-full min-h-0 flex-col gap-4 p-4">
      <header className="flex items-center gap-3">
        <h1 className="text-base font-semibold text-ink">Accounts</h1>
        <span className="text-xs text-ink-faint">
          demo only · refreshed every {POLL_MS / 1000}s
        </span>
        <div className="ml-auto flex items-center gap-2">
          <Button size="xs" onClick={() => setToppingUp(true)} disabled={active === null}>
            Add funds
          </Button>
          <Button size="xs" tone="muted" onClick={reloadBoth}>
            Refresh now
          </Button>
        </div>
      </header>

      {/* Said once, above both tables: a failed read leaves the rows it already had on
          screen (`useRead`'s own "keep"), and without this line those rows would read as
          current (`terminal-accounts` spec, "Odczyt zawiódł"). */}
      {accounts.error !== null && (
        <UnreachableNotice onRetry={accounts.reload}>
          The accounts could not be read — {accounts.error}. What is shown is the last
          answer, not the state now.
        </UnreachableNotice>
      )}

      <div className="overflow-x-auto rounded border border-border">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border text-left text-ink-faint">
              <th className="px-3 py-2 font-medium">Account</th>
              <th className="px-3 py-2 font-medium">Currency</th>
              <th className="px-3 py-2 text-right font-medium">Balance</th>
              <th className="px-3 py-2 text-right font-medium">Available</th>
              <th className="px-3 py-2 text-right font-medium">P/L</th>
              <th className="px-3 py-2 font-medium">Trading</th>
            </tr>
          </thead>
          <tbody>
            {accounts.value.map((account) => (
              <tr key={account.id} className="border-b border-border last:border-b-0">
                <td className="px-3 py-2 text-ink">{account.name}</td>
                <td className="px-3 py-2 text-ink-secondary">{account.currency}</td>
                <td className="px-3 py-2 text-right font-mono text-ink">
                  {account.balance.toFixed(2)}
                </td>
                <td className="px-3 py-2 text-right font-mono text-ink-secondary">
                  {account.available.toFixed(2)}
                </td>
                <td
                  className={`px-3 py-2 text-right font-mono ${
                    account.pnl < 0 ? "text-critical" : "text-ink-secondary"
                  }`}
                >
                  {account.pnl.toFixed(2)}
                </td>
                <td className="px-3 py-2">
                  {account.active ? (
                    <span className="rounded border border-good/40 px-1.5 py-0.5 text-[10px] tracking-wide text-good uppercase">
                      active
                    </span>
                  ) : (
                    <Button size="2xs" tone="muted" onClick={() => setPendingSwitch(account)}>
                      Make active
                    </Button>
                  )}
                </td>
              </tr>
            ))}
            {accounts.status === "loading" && accounts.value.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-3 text-ink-faint">
                  reading the accounts…
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-2">
        <h2 className="text-sm font-semibold text-ink">
          Open positions
          <span className="ml-2 text-xs font-normal text-ink-faint">
            {active === null
              ? "— no active account"
              : `— on ${active.name}, the account being traded`}
          </span>
        </h2>

        {positions.error !== null && (
          <UnreachableNotice onRetry={positions.reload}>
            The open positions could not be read — {positions.error}.
          </UnreachableNotice>
        )}

        <div className="min-h-0 flex-1 overflow-auto rounded border border-border">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border text-left text-ink-faint">
                <th className="px-3 py-2 font-medium">Symbol</th>
                <th className="px-3 py-2 font-medium">Direction</th>
                <th className="px-3 py-2 text-right font-medium">Size</th>
                <th className="px-3 py-2 text-right font-medium">Opened at</th>
                <th className="px-3 py-2 text-right font-medium">P/L</th>
              </tr>
            </thead>
            <tbody>
              {positions.value.map((position) => (
                <tr key={position.id} className="border-b border-border last:border-b-0">
                  <td className="px-3 py-2 text-ink">{position.symbol}</td>
                  <td className="px-3 py-2 text-ink-secondary">{position.direction}</td>
                  <td className="px-3 py-2 text-right font-mono text-ink-secondary">
                    {position.size}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-ink-secondary">
                    {position.openLevel === null ? "—" : position.openLevel}
                  </td>
                  <td
                    className={`px-3 py-2 text-right font-mono ${
                      (position.pnl ?? 0) < 0 ? "text-critical" : "text-ink-secondary"
                    }`}
                  >
                    {position.pnl === null ? "—" : position.pnl.toFixed(2)}
                  </td>
                </tr>
              ))}
              {positions.status !== "loading" && positions.value.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-3 py-3 text-ink-faint">
                    nothing open on this account
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {toppingUp && active !== null && (
        <TopUpDialog
          account={active}
          onConfirm={async (amount) => {
            await client.topUp(amount, new AbortController().signal);
            reloadBoth();
          }}
          onClose={() => setToppingUp(false)}
        />
      )}

      {pendingSwitch !== null && (
        <ConfirmDialog
          title={`Trade on ${pendingSwitch.name}?`}
          confirmLabel="Switch"
          busyLabel="Switching…"
          fallbackError="the account could not be switched"
          onConfirm={async () => {
            await client.switchAccount(pendingSwitch.id, new AbortController().signal);
            reloadBoth();
          }}
          onClose={() => setPendingSwitch(null)}
        >
          {/* Said before, not after: the cost of this lands in a part of the system this
              screen does not show (`terminal-accounts` spec, "Przełączenie konta mówi, co
              zrywa"). */}
          <p className="text-sm text-ink-secondary">
            Every order placed after this acts on <strong>{pendingSwitch.name}</strong>.
          </p>
          <p className="mt-2 text-sm text-ink-secondary">
            Switching also ends the provider's quote stream: the archive stops receiving
            candles for a few seconds and reconnects on its own. That gap is in the
            collected data, not on this screen.
          </p>
        </ConfirmDialog>
      )}
    </section>
  );
}

/** Stable identities, so a render with nothing to show is not a new array every time. */
const EMPTY_ACCOUNTS: DemoAccount[] = [];
const EMPTY_POSITIONS: Awaited<ReturnType<AccountsApi["listPositions"]>> = [];

function TopUpDialog({
  account,
  onConfirm,
  onClose,
}: {
  account: DemoAccount;
  onConfirm(amount: number): Promise<void>;
  onClose(): void;
}) {
  const [raw, setRaw] = useState("1000");
  const amount = Number(raw);
  // Zero is the one amount the module refuses by itself, and a blank box is not an amount.
  const usable = raw.trim() !== "" && Number.isFinite(amount) && amount !== 0;

  return (
    <ConfirmDialog
      title={`Move funds on ${account.name}`}
      confirmLabel="Apply"
      busyLabel="Applying…"
      confirmDisabled={!usable}
      fallbackError="the balance could not be changed"
      onConfirm={() => onConfirm(amount)}
      onClose={onClose}
    >
      <label className="block text-sm text-ink-secondary">
        Amount in {account.currency}
        <input
          value={raw}
          onChange={(event) => setRaw(event.target.value)}
          inputMode="decimal"
          aria-label="Amount"
          className="mt-1 w-full rounded border border-border bg-sunken px-2 py-1 font-mono text-sm text-ink focus:border-primary focus:outline-none"
        />
      </label>
      {/* Negative is not a trap to guard against: setting up a thin account is how a test
          of "what happens when it runs low" begins (`terminal-accounts` spec). */}
      <p className="mt-2 text-xs text-ink-faint">
        Negative takes funds away. The provider keeps its own limits on the balance, on one
        adjustment and on how many a day — a refusal says which.
      </p>
    </ConfirmDialog>
  );
}
