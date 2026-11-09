import { useCallback, useMemo, useState } from "react";
import { createAccountsApi, type AccountsApi, type DemoAccount } from "./accountsApi";
import { LiveAccountSection } from "./LiveAccountSection";
import { createLiveAccountApi, type LiveAccountApi } from "./liveAccountApi";
import { gatewayIdentity } from "../data/marketData";
import { resolveEndpoints, resolveLiveGatewayHttp } from "../data/config";
import { useRead } from "../data/query";
import { Button } from "../ui/Button";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { UnreachableNotice } from "../ui/UnreachableNotice";

/**
 * The demo accounts and the money on them. Any account's positions can be looked at without making it active: the
 * gateway keeps a session per account, and switching would move every caller that names none — never done for a read.
 */

/** How often the screen re-asks. The provider counts ten requests a second per account against everything
 *  this system does, and five seconds is faster than an operator can act on. */
const POLL_MS = 5000;

export function AccountsView({
  api,
  liveApi,
}: { api?: AccountsApi; liveApi?: LiveAccountApi | null } = {}) {
  const client = useMemo(
    () => api ?? createAccountsApi(resolveEndpoints().gatewayHttp, gatewayIdentity),
    [api],
  );
  // Absent unless the terminal was built with the live account's address (`terminal-accounts`).
  const live = useMemo(() => {
    if (liveApi !== undefined) return liveApi;
    const base = resolveLiveGatewayHttp();
    return base === null ? null : createLiveAccountApi(base, gatewayIdentity);
  }, [liveApi]);

  const accounts = useRead<DemoAccount[]>({
    key: ["gateway", "accounts"],
    read: (signal) => client.listAccounts(signal),
    initial: EMPTY_ACCOUNTS,
    fallbackMessage: "could not read the accounts",
    pollMs: POLL_MS,
  });

  // Null follows the active account, whichever that is by the next poll.
  const [viewingId, setViewingId] = useState<string | null>(null);

  const positions = useRead({
    key: ["gateway", "positions", viewingId ?? "active"],
    read: (signal) => client.listPositions(signal, viewingId),
    initial: EMPTY_POSITIONS,
    fallbackMessage: "could not read the open positions",
    pollMs: POLL_MS,
  });

  const active = accounts.value.find((account) => account.active) ?? null;
  const viewed =
    viewingId === null
      ? active
      : (accounts.value.find((account) => account.id === viewingId) ?? null);
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
          <Button size="xs" onClick={() => setToppingUp(true)} disabled={viewed === null}>
            Add funds
          </Button>
          <Button size="xs" tone="muted" onClick={reloadBoth}>
            Refresh now
          </Button>
        </div>
      </header>

      {live !== null && <LiveAccountSection api={live} pollMs={POLL_MS} />}

      {/* Said once, above both tables: a failed read leaves the rows it already had on screen, and
          without this line those rows would read as current. */}
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
              <tr
                key={account.id}
                className={`border-b border-border last:border-b-0 ${
                  account.id === viewed?.id ? "bg-sunken" : ""
                }`}
              >
                <td className="px-3 py-2 text-ink">
                  <button
                    type="button"
                    className="hover:underline"
                    aria-pressed={account.id === viewed?.id}
                    onClick={() => setViewingId(account.active ? null : account.id)}
                  >
                    {account.name}
                  </button>
                </td>
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
            {viewed === null
              ? "— no active account"
              : viewed.active
                ? `— on ${viewed.name}, the active account`
                : `— on ${viewed.name}, not the active account`}
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

      {toppingUp && viewed !== null && (
        <TopUpDialog
          account={viewed}
          onConfirm={async (amount) => {
            await client.topUp(amount, new AbortController().signal, viewingId);
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
            setViewingId(null);
            reloadBoth();
          }}
          onClose={() => setPendingSwitch(null)}
        >
          {/* Said before, not after: the cost of this lands in a part of the system this screen does
              not show. */}
          <p className="text-sm text-ink-secondary">
            Every order that names no account acts on <strong>{pendingSwitch.name}</strong>{" "}
            after this: the conversation, teams without an account of their own and the
            operator's MCP client.
          </p>
          <p className="mt-2 text-sm text-ink-secondary">
            Teams with an account of their own keep trading where they were. To look at an
            account's positions, click its name instead.
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
