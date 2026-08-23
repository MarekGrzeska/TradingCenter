import { ConfirmDialog } from "../ui/ConfirmDialog";
import type { PolymarketApi, TrackedEvent } from "./polymarketApi";

/**
 * Removing an observation — **the one place in this system that can**, and the only way an
 * event leaves the list.
 *
 * No tool the model holds does this. Eight tools reach that module and two of them write;
 * what they write is the watch list, and both of them only add to it. So this dialog is not
 * a convenience: without it the capability has no door at all, and the only way to use it
 * would be `psql` or a temporary entry in a caller list — a workaround for the one act that
 * cannot be undone.
 *
 * **There is nothing to choose between here, and that is the point.** The dialog used to end
 * with "to stop collecting instead, without losing anything, use Stop tracking" — a second
 * act, standing next to this one, whose whole job was producing an observation that neither
 * collected nor left. It is gone, so the confirmation names one outcome rather than steering
 * between two (specs/terminal-polymarket, "Kasowanie zebranej historii jest tutaj i wymaga
 * potwierdzenia").
 *
 * **Irreversible here means something stronger than it does anywhere else in this
 * terminal.** A deleted candle can be fetched again; the gateway still has it. Polymarket
 * does not give back the history of a market that has resolved, and reaches only so far
 * for the rest. The confirmation says that, because "this cannot be undone" is a sentence
 * an operator has read a hundred times and this is one of the few places it is literally
 * true.
 */
export function RemoveEventDialog({
  client,
  event,
  onClose,
  onRemoved,
}: {
  client: PolymarketApi;
  event: TrackedEvent;
  onClose(): void;
  onRemoved(): void;
}) {
  return (
    <ConfirmDialog
      title="Remove this observation"
      confirmLabel="Remove"
      busyLabel="Removing…"
      tone="danger"
      fallbackError="the observation could not be removed"
      onConfirm={async () => {
        await client.removeEvent(event.providerEventId, new AbortController().signal);
        onRemoved();
      }}
      onClose={onClose}
    >
      <div className="flex flex-col gap-2 text-xs">
        <p className="text-ink-secondary">
          <span className="text-ink">{event.title}</span> leaves the list, and every price
          collected for it — every market, every outcome — goes with it.
        </p>
        <p className="text-ink-secondary">
          <strong className="text-ink">Most of it cannot be collected again at any price.</strong>{" "}
          Polymarket does not return the history of a market that has resolved, and reaches
          only so far back for the rest.
        </p>
        <p className="text-ink-faint">
          Tracking it again later starts from an empty archive.
        </p>
      </div>
    </ConfirmDialog>
  );
}
