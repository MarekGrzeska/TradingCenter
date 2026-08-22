import { useState } from "react";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import type { DeletionResult, PolymarketApi, TrackedEvent } from "./polymarketApi";

/**
 * Removing an event's collected history — **the one place in this system that can**.
 *
 * No tool the model holds does this. Nine tools reach that module and three of them write;
 * what they write is the watch list, and the line drawn deliberately elsewhere is that none
 * of them deletes a sample. So this dialog is not a convenience: without it the capability
 * has no door at all, and the only way to use it would be `psql` or a temporary entry in a
 * caller list — a workaround for the one act that cannot be undone.
 *
 * **Irreversible here means something stronger than it does anywhere else in this
 * terminal.** A deleted candle can be fetched again; the gateway still has it. Polymarket
 * does not give back the history of a market that has resolved, and reaches only so far
 * for the rest. The confirmation says that, because "this cannot be undone" is a sentence
 * an operator has read a hundred times and this is one of the few places it is literally
 * true (specs/terminal-polymarket, "Kasowanie zebranej historii jest tutaj i wymaga
 * potwierdzenia").
 */
export function DeleteHistoryDialog({
  client,
  event,
  onClose,
  onDeleted,
}: {
  client: PolymarketApi;
  event: TrackedEvent;
  onClose(): void;
  onDeleted(): void;
}) {
  const [result, setResult] = useState<DeletionResult | null>(null);

  if (result !== null) {
    return (
      <ConfirmDialog
        title="History removed"
        confirmLabel="Close"
        busyLabel="Closing…"
        cancelLabel={null}
        onConfirm={onClose}
        onClose={onClose}
      >
        <p className="text-xs text-ink-secondary">
          {result.samplesDeleted} sample(s) and {result.rangesDeleted} collected range(s)
          were removed for <span className="text-ink">{event.title}</span>. The event is
          still tracked, and collection continues from now.
        </p>
      </ConfirmDialog>
    );
  }

  return (
    <ConfirmDialog
      title="Remove the collected history"
      confirmLabel="Remove history"
      busyLabel="Removing…"
      tone="danger"
      fallbackError="the history could not be removed"
      // The count is worth showing and the list underneath will not show it, so the dialog
      // stays up and swaps itself for the result.
      closeOnSuccess={false}
      onConfirm={async () => {
        const deleted = await client.deleteHistory(
          event.providerEventId,
          new AbortController().signal,
        );
        onDeleted();
        setResult(deleted);
      }}
      onClose={onClose}
    >
      <div className="flex flex-col gap-2 text-xs">
        <p className="text-ink-secondary">
          Every price collected for <span className="text-ink">{event.title}</span> — every
          market, every outcome — is removed.
        </p>
        <p className="text-ink-secondary">
          <strong className="text-ink">Most of it cannot be collected again at any price.</strong>{" "}
          Polymarket does not return the history of a market that has resolved, and reaches
          only so far back for the rest.
        </p>
        <p className="text-ink-faint">
          The event stays tracked. To stop collecting instead, without losing anything, use
          “Stop tracking”.
        </p>
      </div>
    </ConfirmDialog>
  );
}
