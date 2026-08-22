import { useState } from "react";
import { Button } from "../ui/Button";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { showToast } from "../ui/toastStore";
import type { Group, PolymarketApi } from "./polymarketApi";

/**
 * The operator's own categories, and nothing more than that.
 *
 * A group is a way of narrowing this list — it is not a property of the market and the
 * module does not collect differently because of one. Deleting one therefore ends no
 * observation and removes no sample, which the dialog says out loud for the same reason
 * the stop-tracking dialog does: a delete button standing near data reads as a delete
 * button for that data (specs/terminal-polymarket, "Grupy obserwacji są operatora").
 *
 * Absent entirely when there are no groups. A row of controls for an empty set is a
 * promise of a part of the screen that is not there.
 */
export function GroupBar({
  client,
  groups,
  selected,
  onSelect,
  onChanged,
}: {
  client: PolymarketApi;
  groups: Group[];
  selected: number | null;
  onSelect(groupId: number | null): void;
  onChanged(): void;
}) {
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [deleting, setDeleting] = useState<Group | null>(null);

  const active = groups.find((entry) => entry.id === selected) ?? null;

  return (
    <nav className="flex flex-wrap items-center gap-2 text-xs">
      {groups.length > 0 && (
        <>
          <span className="text-ink-faint">Groups</span>
          <Button
            size="2xs"
            tone={selected === null ? "primary" : "quiet"}
            onClick={() => onSelect(null)}
          >
            all
          </Button>
          {groups.map((entry) => (
            <Button
              key={entry.id}
              size="2xs"
              tone={selected === entry.id ? "primary" : "quiet"}
              onClick={() => onSelect(entry.id)}
            >
              {entry.name} ({entry.eventCount})
            </Button>
          ))}
        </>
      )}

      <Button size="2xs" tone="quiet" className="ml-auto" onClick={() => setCreating(true)}>
        New group
      </Button>
      {active !== null && (
        <Button size="2xs" tone="quiet" onClick={() => setDeleting(active)}>
          Delete “{active.name}”
        </Button>
      )}

      {creating && (
        <ConfirmDialog
          title="New group"
          confirmLabel="Create"
          busyLabel="Creating…"
          confirmDisabled={name.trim() === ""}
          fallbackError="the group could not be created"
          onConfirm={async () => {
            const created = await client.createGroup(name.trim(), new AbortController().signal);
            setName("");
            onChanged();
            onSelect(created.id);
          }}
          onClose={() => {
            setName("");
            setCreating(false);
          }}
        >
          <div className="flex flex-col gap-1 text-xs">
            <label className="flex flex-col gap-1">
              <span className="text-ink-secondary">Name</span>
              <input
                className="rounded border border-border bg-sunken px-2 py-1 text-ink"
                value={name}
                autoFocus
                placeholder="macro"
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            {/* Outside the label on purpose: inside it, the hint joins the field's
                accessible name and the field stops being findable by what it is called. */}
            <span className="text-ink-faint">
              A way of narrowing this list. It changes nothing about what is collected.
            </span>
          </div>
        </ConfirmDialog>
      )}

      {deleting !== null && (
        <ConfirmDialog
          title={`Delete the group “${deleting.name}”`}
          confirmLabel="Delete group"
          busyLabel="Deleting…"
          tone="danger"
          fallbackError="the group could not be deleted"
          onConfirm={async () => {
            await client.deleteGroup(deleting.id, new AbortController().signal);
            onSelect(null);
            onChanged();
            showToast({
              key: `polymarket-group-deleted-${deleting.id}`,
              title: `Group “${deleting.name}” deleted`,
              detail: "Its events are still tracked and their history is untouched.",
            });
            setDeleting(null);
          }}
          onClose={() => setDeleting(null)}
        >
          <p className="text-xs text-ink-secondary">
            The {deleting.eventCount} event(s) in it{" "}
            <strong className="text-ink">stay tracked</strong>, and none of their collected
            history is removed. Only the grouping goes.
          </p>
        </ConfirmDialog>
      )}
    </nav>
  );
}
