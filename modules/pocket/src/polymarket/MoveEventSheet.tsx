import { useId, useState } from "react";
import type { Group, PolymarketApi, TrackedEvent } from "./api";
import { Sheet } from "../ui/Sheet";
import { Button } from "../ui/Button";
import styles from "./Sheets.module.css";

export interface MoveEventSheetProps {
  api: PolymarketApi;
  event: TrackedEvent;
  groups: Group[];
  onClose: () => void;
  onMoved: (notice: string) => void;
}

/** Filing an event under another group. Only groups that exist are offered: a new one typed here would
 *  be one more spelling of a category the operator already has. */
export function MoveEventSheet({ api, event, groups, onClose, onMoved }: MoveEventSheetProps) {
  const selectId = useId();
  const current = groups.find((group) => group.name === event.group);
  const [choice, setChoice] = useState(current === undefined ? "" : String(current.id));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const move = async () => {
    const target = groups.find((group) => String(group.id) === choice);
    setBusy(true);
    setError(null);
    try {
      await api.assignGroup(event.id, target?.id ?? null, new AbortController().signal);
      onMoved(
        target === undefined
          ? `${event.title} is in no group now.`
          : `${event.title} is in “${target.name}” now.`,
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not move that event.");
      setBusy(false);
    }
  };

  return (
    <Sheet
      title="Move to a group"
      busy={busy}
      onClose={onClose}
      actions={
        <>
          <Button onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button tone="primary" onClick={() => void move()} disabled={busy}>
            {busy ? "Moving…" : "Move"}
          </Button>
        </>
      }
    >
      <p className={styles.text}>
        <strong className={styles.strong}>{event.title}</strong> stays tracked with its history;
        only its group changes.
      </p>
      <div className={styles.field}>
        <label className={styles.label} htmlFor={selectId}>
          Group
        </label>
        <select
          id={selectId}
          className={styles.input}
          value={choice}
          onChange={(change) => setChoice(change.target.value)}
          disabled={busy}
        >
          <option value="">no group</option>
          {groups.map((group) => (
            <option key={group.id} value={group.id}>
              {group.name}
            </option>
          ))}
        </select>
      </div>

      {error === null ? null : (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
    </Sheet>
  );
}
