import { ConfirmDialog } from "../ui/ConfirmDialog";
import type { PolymarketApi, TrackedEvent } from "./polymarketApi";

/**
 * Ending an observation — which stops the sampling and **keeps every sample already
 * collected**.
 *
 * The dialog exists to say that before it happens, and the requirement is written down
 * because the confusion is structural rather than careless: a button that stops collecting,
 * standing next to collected data, reads as a button that removes it. The two are separate
 * acts here on purpose and only one of them cannot be undone
 * (specs/terminal-polymarket, "Zakończenie obserwacji nie rusza danych i mówi o tym").
 */
export function EndTrackingDialog({
  client,
  event,
  onClose,
  onEnded,
}: {
  client: PolymarketApi;
  event: TrackedEvent;
  onClose(): void;
  onEnded(): void;
}) {
  return (
    <ConfirmDialog
      title="Stop tracking this event"
      confirmLabel="Stop tracking"
      busyLabel="Stopping…"
      fallbackError="the observation could not be ended"
      onConfirm={async () => {
        await client.endTracking(event.providerEventId, new AbortController().signal);
        onEnded();
      }}
      onClose={onClose}
    >
      <div className="flex flex-col gap-2 text-xs">
        <p className="text-ink-secondary">
          <span className="text-ink">{event.title}</span> stops being sampled. No new prices
          are collected for it.
        </p>
        <p className="text-ink-secondary">
          <strong className="text-ink">Everything already collected stays.</strong> Removing
          it is a separate action, and it is the one that cannot be undone.
        </p>
      </div>
    </ConfirmDialog>
  );
}
