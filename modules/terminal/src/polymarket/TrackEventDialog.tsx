import { useState } from "react";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import type { Group, PolymarketApi } from "./polymarketApi";

/**
 * Either spelling names the same observation — an address out of the browser, or a slug — so the module resolves
 * both and this asks one field. Already tracked and the ceiling are answers, not failures, and read as such.
 */
export function TrackEventDialog({
  client,
  groups,
  onClose,
  onTracked,
}: {
  client: PolymarketApi;
  groups: Group[];
  onClose(): void;
  onTracked(): void;
}) {
  const [reference, setReference] = useState("");
  const [group, setGroup] = useState("");
  const [alreadyTracked, setAlreadyTracked] = useState<string | null>(null);

  if (alreadyTracked !== null) {
    return (
      <ConfirmDialog
        title="Already tracked"
        confirmLabel="Close"
        busyLabel="Closing…"
        cancelLabel={null}
        onConfirm={onClose}
        onClose={onClose}
      >
        <p className="text-xs text-ink-secondary">
          <span className="text-ink">{alreadyTracked}</span> is already under observation.
          No second observation was created and its collected history is untouched.
        </p>
      </ConfirmDialog>
    );
  }

  return (
    <ConfirmDialog
      title="Track an event"
      confirmLabel="Track"
      busyLabel="Asking the module…"
      confirmDisabled={reference.trim() === ""}
      fallbackError="the event could not be tracked"
      // The already-tracked answer swaps this dialog for the one above rather than closing
      // it, because there is something to say that the list will not show.
      closeOnSuccess={false}
      onConfirm={async () => {
        const result = await client.trackEvent(
          reference.trim(),
          new AbortController().signal,
          group.trim() === "" ? undefined : group.trim(),
        );
        onTracked();
        if (result.alreadyTracked) {
          setAlreadyTracked(result.event.title);
          return;
        }
        onClose();
      }}
      onClose={onClose}
    >
      <div className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-ink-secondary">Event address or slug</span>
          <input
            className="rounded border border-border bg-sunken px-2 py-1 text-ink"
            value={reference}
            autoFocus
            placeholder="https://polymarket.com/event/… or fed-cuts-in-march"
            onChange={(e) => setReference(e.target.value)}
          />
          <span className="text-ink-faint">
            Both name the same observation — paste whichever you have.
          </span>
        </label>

        <label className="flex flex-col gap-1 text-xs">
          <span className="text-ink-secondary">Group (optional)</span>
          <input
            className="rounded border border-border bg-sunken px-2 py-1 text-ink"
            value={group}
            list="polymarket-groups"
            placeholder="macro"
            onChange={(e) => setGroup(e.target.value)}
          />
          <datalist id="polymarket-groups">
            {groups.map((entry) => (
              <option key={entry.id} value={entry.name} />
            ))}
          </datalist>
          <span className="text-ink-faint">Created if it does not exist yet.</span>
        </label>

        <p className="text-xs text-ink-faint">
          Sampling starts immediately, once a minute, and the past is filled in behind it as
          far back as the provider reaches.
        </p>
      </div>
    </ConfirmDialog>
  );
}
