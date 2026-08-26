import { ConfirmDialog } from "../ui/ConfirmDialog";
import type { PolymarketApi, TrackedEvent } from "./polymarketApi";

/**
 * **The one place in this system that can remove an observation** — no tool the model holds does, so without this
 * the capability has no door. Polymarket does not give back a resolved market's history: undone means undone.
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
