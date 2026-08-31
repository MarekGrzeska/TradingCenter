import { useId, useState } from "react";
import type { PolymarketApi } from "./api";
import { Sheet } from "../ui/Sheet";
import { Button } from "../ui/Button";
import styles from "./Sheets.module.css";

export interface TrackEventSheetProps {
  api: PolymarketApi;
  /** The groups that already exist, offered as suggestions. Typing a new one creates it, which is
   *  what the archive does with an unknown name. */
  groups: string[];
  onClose: () => void;
  /** Told what happened, because an event already observed is a different sentence from a new one:
   *  no second observation was created and no history was disturbed. */
  onTracked: (title: string, alreadyTracked: boolean) => void;
}

export function TrackEventSheet({ api, groups, onClose, onTracked }: TrackEventSheetProps) {
  const referenceId = useId();
  const groupId = useId();
  const listId = useId();
  const [reference, setReference] = useState("");
  const [group, setGroup] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    const trimmed = reference.trim();
    if (!trimmed) {
      setError("Paste the event's address on polymarket.com, or its slug.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await api.trackEvent(
        trimmed,
        new AbortController().signal,
        group.trim() || undefined,
      );
      onTracked(result.event.title, result.alreadyTracked);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not track that event.");
      setBusy(false);
    }
  };

  return (
    <Sheet
      title="Track an event"
      busy={busy}
      onClose={onClose}
      actions={
        <>
          <Button onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button tone="primary" onClick={() => void submit()} disabled={busy}>
            {busy ? "Tracking…" : "Track"}
          </Button>
        </>
      }
    >
      <div className={styles.field}>
        <label className={styles.label} htmlFor={referenceId}>
          Event address or slug
        </label>
        <input
          id={referenceId}
          className={styles.input}
          // `url` would refuse a bare slug, which the archive accepts and a model already has.
          type="text"
          inputMode="url"
          autoComplete="off"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          placeholder="https://polymarket.com/event/..."
          value={reference}
          onChange={(event) => setReference(event.target.value)}
          disabled={busy}
        />
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor={groupId}>
          Group (optional)
        </label>
        <input
          id={groupId}
          className={styles.input}
          list={listId}
          autoComplete="off"
          placeholder="Created if it does not exist yet"
          value={group}
          onChange={(event) => setGroup(event.target.value)}
          disabled={busy}
        />
        <datalist id={listId}>
          {groups.map((name) => (
            <option key={name} value={name} />
          ))}
        </datalist>
      </div>

      {error === null ? null : (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
    </Sheet>
  );
}
