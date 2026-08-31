import { useState } from "react";
import type { PolymarketApi, TrackedEvent } from "./api";
import { Sheet } from "../ui/Sheet";
import { Button } from "../ui/Button";
import styles from "./Sheets.module.css";

export interface RemoveEventSheetProps {
  api: PolymarketApi;
  event: TrackedEvent;
  onClose: () => void;
  onRemoved: (title: string) => void;
}

/** The one act in this app that cannot be undone. There is no stopping without removing — the archive
 *  has no third state — so the sheet says what goes rather than asking "are you sure". */
export function RemoveEventSheet({ api, event, onClose, onRemoved }: RemoveEventSheetProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const remove = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.removeEvent(event.providerEventId, new AbortController().signal);
      onRemoved(event.title);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not remove that observation.");
      setBusy(false);
    }
  };

  return (
    <Sheet
      title="Remove this observation"
      busy={busy}
      onClose={onClose}
      actions={
        <>
          <Button onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button tone="danger" onClick={() => void remove()} disabled={busy}>
            {busy ? "Removing…" : "Remove"}
          </Button>
        </>
      }
    >
      <p className={styles.text}>
        <strong className={styles.strong}>{event.title}</strong> leaves the list with every price
        ever collected for it. Collection cannot be paused instead, and nothing here brings the
        history back.
      </p>

      {error === null ? null : (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
    </Sheet>
  );
}
