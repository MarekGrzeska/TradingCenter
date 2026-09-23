import { useId, useState } from "react";
import type { Group, PolymarketApi } from "./api";
import { Sheet } from "../ui/Sheet";
import { Button } from "../ui/Button";
import styles from "./Sheets.module.css";

export interface GroupsSheetProps {
  api: PolymarketApi;
  groups: Group[];
  onClose: () => void;
  onChanged: (notice: string) => void;
}

/** The operator's categories, renamed and deleted from a phone. A group holds no data, so deleting one
 *  ends no observation; deleting it *into* another is how two spellings of one category become one. */
export function GroupsSheet({ api, groups, onClose, onChanged }: GroupsSheetProps) {
  const [editing, setEditing] = useState<Group | null>(null);

  return editing === null ? (
    <Sheet
      title="Groups"
      onClose={onClose}
      actions={<Button onClick={onClose}>Close</Button>}
    >
      <ul className={styles.list}>
        {groups.map((group) => (
          <li key={group.id}>
            <button type="button" className={styles.row} onClick={() => setEditing(group)}>
              <span className={styles.strong}>{group.name}</span>
              <span className={styles.count}>
                {group.eventCount} {group.eventCount === 1 ? "event" : "events"}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </Sheet>
  ) : (
    <EditGroup
      api={api}
      group={editing}
      others={groups.filter((group) => group.id !== editing.id)}
      onBack={() => setEditing(null)}
      onChanged={onChanged}
    />
  );
}

function EditGroup({
  api,
  group,
  others,
  onBack,
  onChanged,
}: {
  api: PolymarketApi;
  group: Group;
  others: Group[];
  onBack: () => void;
  onChanged: (notice: string) => void;
}) {
  const nameId = useId();
  const moveId = useId();
  const [name, setName] = useState(group.name);
  const [moveTo, setMoveTo] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const act = async (work: () => Promise<string>) => {
    setBusy(true);
    setError(null);
    try {
      onChanged(await work());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The archive refused that.");
      setBusy(false);
    }
  };

  const rename = () =>
    act(async () => {
      const renamed = await api.renameGroup(group.id, name.trim(), new AbortController().signal);
      return `“${group.name}” is called “${renamed.name}” now.`;
    });

  const remove = () =>
    act(async () => {
      const target = others.find((other) => String(other.id) === moveTo);
      // A target gone since the list was read would turn a merge into a plain delete without a word.
      if (moveTo !== "" && target === undefined) {
        throw new Error("The group chosen for its events is gone. Choose again.");
      }
      await api.deleteGroup(group.id, new AbortController().signal, target?.id);
      return target === undefined
        ? `“${group.name}” is gone. Its events are still tracked, in no group.`
        : `“${group.name}” is merged into “${target.name}”. Nothing collected was touched.`;
    });

  const unchanged = name.trim() === "" || name.trim() === group.name;

  return (
    <Sheet
      title={`Group “${group.name}”`}
      busy={busy}
      onClose={onBack}
      actions={
        <>
          <Button onClick={onBack} disabled={busy}>
            Back
          </Button>
          <Button tone="primary" onClick={() => void rename()} disabled={busy || unchanged}>
            Rename
          </Button>
        </>
      }
    >
      <div className={styles.field}>
        <label className={styles.label} htmlFor={nameId}>
          Name
        </label>
        <input
          id={nameId}
          className={styles.input}
          autoComplete="off"
          value={name}
          onChange={(event) => setName(event.target.value)}
          disabled={busy}
        />
      </div>

      <div className={styles.danger}>
        <p className={styles.text}>
          Deleting the group keeps its {group.eventCount}{" "}
          {group.eventCount === 1 ? "event" : "events"} tracked with every price collected.
        </p>
        {group.eventCount > 0 && others.length > 0 ? (
          <div className={styles.field}>
            <label className={styles.label} htmlFor={moveId}>
              Move its events to
            </label>
            <select
              id={moveId}
              className={styles.input}
              value={moveTo}
              onChange={(event) => setMoveTo(event.target.value)}
              disabled={busy}
            >
              <option value="">no group</option>
              {others.map((other) => (
                <option key={other.id} value={other.id}>
                  {other.name}
                </option>
              ))}
            </select>
          </div>
        ) : null}
        <Button tone="danger" onClick={() => void remove()} disabled={busy}>
          Delete group
        </Button>
      </div>

      {error === null ? null : (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
    </Sheet>
  );
}
