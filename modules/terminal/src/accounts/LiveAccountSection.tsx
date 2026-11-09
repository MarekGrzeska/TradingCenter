import { useCallback, useState } from "react";
import type { AccountPosition, DemoAccount } from "./accountsApi";
import type { CloseAllItem, LiveAccountApi, LiveWorkingOrder } from "./liveAccountApi";
import { useRead } from "../data/query";
import { Button } from "../ui/Button";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { UnreachableNotice } from "../ui/UnreachableNotice";

/**
 * The live account, apart from the demo ones so the two cannot be mistaken (specs/terminal-accounts): read only, plus the
 * way out — close every position and cancel every working order, after a question that says how many and that it is real.
 */
export function LiveAccountSection({ api, pollMs }: { api: LiveAccountApi; pollMs: number }) {
  const accounts = useRead<DemoAccount[]>({
    key: ["live-gateway", "accounts"],
    read: (signal) => api.listAccounts(signal),
    initial: NO_ACCOUNTS,
    fallbackMessage: "could not read the live account",
    pollMs,
  });
  const positions = useRead<AccountPosition[]>({
    key: ["live-gateway", "positions"],
    read: (signal) => api.listPositions(signal),
    initial: NO_POSITIONS,
    fallbackMessage: "could not read the live account's positions",
    pollMs,
  });
  const orders = useRead<LiveWorkingOrder[]>({
    key: ["live-gateway", "working-orders"],
    read: (signal) => api.listWorkingOrders(signal),
    initial: NO_ORDERS,
    fallbackMessage: "could not read the live account's working orders",
    pollMs,
  });
  const [confirming, setConfirming] = useState(false);
  const [outcome, setOutcome] = useState<CloseAllItem[] | null>(null);

  const reload = useCallback(() => {
    accounts.reload();
    positions.reload();
    orders.reload();
  }, [accounts, positions, orders]);

  const error = accounts.error ?? positions.error ?? orders.error;
  const account = accounts.value[0] ?? null;
  const open = positions.value.length + orders.value.length;

  return (
    <section
      aria-label="Live account"
      className="flex flex-col gap-2 rounded border-2 border-critical/60 bg-critical/5 p-3"
    >
      <header className="flex items-center gap-3">
        <h2 className="text-sm font-semibold text-critical">LIVE ACCOUNT · real money</h2>
        <span className="text-xs text-ink-faint">read only · refreshed every {pollMs / 1000}s</span>
        <div className="ml-auto">
          <Button
            size="xs"
            tone="critical"
            onClick={() => setConfirming(true)}
            // A failed read is no proof the account is flat: the way out stays open when the screen cannot see.
            disabled={error === null && open === 0}
          >
            Close everything
          </Button>
        </div>
      </header>

      {error !== null && (
        <UnreachableNotice onRetry={reload}>
          The live account could not be read — {error}. Nothing here is the state now.
        </UnreachableNotice>
      )}

      {account !== null && (
        <p className="text-xs text-ink-secondary">
          <span className="font-semibold text-ink">{account.name}</span> · {account.currency} · balance{" "}
          <span className="font-mono">{account.balance.toFixed(2)}</span> · available{" "}
          <span className="font-mono">{account.available.toFixed(2)}</span> · P/L{" "}
          <span className={`font-mono ${account.pnl < 0 ? "text-critical" : ""}`}>
            {account.pnl.toFixed(2)}
          </span>
        </p>
      )}

      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-border text-left text-ink-faint">
            <th className="px-2 py-1 font-medium">Open</th>
            <th className="px-2 py-1 font-medium">Symbol</th>
            <th className="px-2 py-1 font-medium">Direction</th>
            <th className="px-2 py-1 text-right font-medium">Size</th>
            <th className="px-2 py-1 text-right font-medium">Level</th>
            <th className="px-2 py-1 text-right font-medium">P/L</th>
          </tr>
        </thead>
        <tbody>
          {positions.value.map((position) => (
            <tr key={position.id} className="border-b border-border last:border-b-0">
              <td className="px-2 py-1 text-ink-faint">position</td>
              <td className="px-2 py-1 text-ink">{position.symbol}</td>
              <td className="px-2 py-1 text-ink-secondary">{position.direction}</td>
              <td className="px-2 py-1 text-right font-mono">{position.size}</td>
              <td className="px-2 py-1 text-right font-mono">{position.openLevel ?? "—"}</td>
              <td
                className={`px-2 py-1 text-right font-mono ${(position.pnl ?? 0) < 0 ? "text-critical" : ""}`}
              >
                {position.pnl === null ? "—" : position.pnl.toFixed(2)}
              </td>
            </tr>
          ))}
          {orders.value.map((order) => (
            <tr key={order.id} className="border-b border-border last:border-b-0">
              <td className="px-2 py-1 text-ink-faint">{order.orderType.toLowerCase()} order</td>
              <td className="px-2 py-1 text-ink">{order.symbol}</td>
              <td className="px-2 py-1 text-ink-secondary">{order.direction}</td>
              <td className="px-2 py-1 text-right font-mono">{order.size}</td>
              <td className="px-2 py-1 text-right font-mono">{order.level ?? "—"}</td>
              <td className="px-2 py-1 text-right">—</td>
            </tr>
          ))}
          {error === null && open === 0 && positions.status !== "loading" && (
            <tr>
              <td colSpan={6} className="px-2 py-2 text-ink-faint">
                nothing open on the live account
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {confirming && (
        <ConfirmDialog
          title="Close everything on the live account?"
          confirmLabel="Close everything"
          busyLabel="Closing…"
          tone="danger"
          fallbackError="the live account could not be closed out"
          onConfirm={async () => {
            setOutcome(await api.closeAll(new AbortController().signal));
            reload();
          }}
          onClose={() => setConfirming(false)}
        >
          <p className="text-sm text-ink-secondary">
            This is the <strong>live account — real money</strong>. It closes{" "}
            {positions.value.length} {positions.value.length === 1 ? "position" : "positions"} and
            cancels {orders.value.length} working {orders.value.length === 1 ? "order" : "orders"} at
            the market, now.
          </p>
        </ConfirmDialog>
      )}

      {outcome !== null && (
        <div role="status" className="rounded border border-border bg-panel p-2 text-xs">
          <p className="mb-1 font-semibold text-ink">What became of each</p>
          <ul>
            {outcome.map((item) => (
              <li key={`${item.kind}-${item.id}`} className={item.status === "REJECTED" || item.status === "PENDING" ? "text-critical" : "text-ink-secondary"}>
                {item.kind === "position" ? "position" : "working order"} {item.id}
                {item.symbol ? ` (${item.symbol})` : ""}: {item.status}
                {item.reason ? ` — ${item.reason}` : ""}
              </li>
            ))}
            {outcome.length === 0 && <li className="text-ink-faint">nothing was open</li>}
          </ul>
          <Button size="2xs" tone="muted" onClick={() => setOutcome(null)}>
            Dismiss
          </Button>
        </div>
      )}
    </section>
  );
}

const NO_ACCOUNTS: DemoAccount[] = [];
const NO_POSITIONS: AccountPosition[] = [];
const NO_ORDERS: LiveWorkingOrder[] = [];
