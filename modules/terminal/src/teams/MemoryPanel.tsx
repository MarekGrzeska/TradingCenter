import { useState } from "react";
import { useRead } from "../data/query";
import { Button } from "../ui/Button";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { formatInstant } from "../ui/formatTime";
import type { TeamMemory, TeamMemoryEntry, TeamsApi } from "./teamsApi";

/** Before the first answer: not "this team remembers nothing", which is a different
 *  thing and is drawn differently below. */
const NOT_READ_YET: TeamMemory | null = null;

/**
 * What a team learned in earlier runs — specs/terminal-teams, "Pamięć zespołu jest
 * widoczna przy zespole i to operator ją prostuje".
 *
 * This is the one thing in the module that changes how the *next* run goes and appears
 * neither in the revision nor in that run's trace. A team that remembered something untrue
 * repeats it at every start and is paid for every time, and an operator with nowhere to see
 * it goes looking through prompts. So: a list, and a way to take one entry out.
 *
 * There is nothing here that writes or edits. A note is an agent deciding to keep
 * something, and a correction is the next note (specs/teams-memory, "Wpis raz zapisany się
 * nie zmienia") — the operator's part is removal, which is why the only action on a row is
 * destructive and asks first.
 */
export function MemoryPanel({
  api,
  teamId,
  teamName,
  onClose,
}: {
  api: TeamsApi;
  teamId: number;
  teamName: string;
  onClose(): void;
}) {
  const [removing, setRemoving] = useState<TeamMemoryEntry | null>(null);

  const memory = useRead({
    key: ["teams", teamId, "memory"],
    read: (signal) => api.memory(teamId, signal),
    initial: NOT_READ_YET,
    fallbackMessage: "could not read this team's memory",
  });

  const entries = memory.value?.entries ?? [];
  const total = memory.value?.total ?? 0;
  const hidden = total - entries.length;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex items-center gap-2 border-b border-border p-2">
        <Button onClick={onClose}>← {teamName}</Button>
        <h2 className="text-sm font-semibold text-ink">Memory</h2>
      </header>

      <div className="flex-1 overflow-auto p-4">
        {memory.error && <p className="mb-3 text-sm text-critical">{memory.error}</p>}

        <p className="mb-3 max-w-prose text-xs text-ink-muted">
          Notes this team's agents chose to keep for later runs. Every run of this team
          reads them, whichever revision it runs. Agents cannot edit or remove a note — a
          correction is another note, and taking one out is yours.
        </p>

        {memory.value === null && !memory.error && (
          <p className="text-sm text-ink-muted">Reading…</p>
        )}

        {memory.value !== null && entries.length === 0 && (
          <p className="text-sm text-ink-muted">
            This team has not remembered anything yet. Notes appear here once an agent
            carrying the <code>memory_write</code> tool decides to keep one.
          </p>
        )}

        {entries.length > 0 && (
          <ul className="flex flex-col gap-2">
            {entries.map((entry) => (
              <li
                key={entry.id}
                className="rounded border border-border bg-panel p-3"
              >
                <div className="mb-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-faint">
                  <span className="text-ink-muted">{entry.authorAgentKey}</span>
                  <span>{formatInstant(entry.createdAt)}</span>
                  {/* An entry outlives its run, so this is missing rather than zero. */}
                  {entry.runId !== null && <span>run #{entry.runId}</span>}
                  <span className="ml-auto">
                    <Button tone="muted" onClick={() => setRemoving(entry)}>
                      Remove
                    </Button>
                  </span>
                </div>
                <p className="whitespace-pre-wrap text-sm text-ink">{entry.content}</p>
              </li>
            ))}
          </ul>
        )}

        {hidden > 0 && (
          // Never a silent cut: the same rule the tool reads under, said to the operator.
          <p className="mt-3 text-xs text-ink-faint">
            Showing the {entries.length} newest of {total} notes.
          </p>
        )}
      </div>

      {removing && (
        <ConfirmDialog
          title="Remove this note?"
          confirmLabel="Remove"
          busyLabel="Removing…"
          tone="danger"
          fallbackError="the note could not be removed"
          onConfirm={async () => {
            await api.deleteMemory(teamId, removing.id, new AbortController().signal);
            memory.reload();
          }}
          onClose={() => setRemoving(null)}
        >
          <p className="text-sm text-ink-muted">
            Later runs will stop reading it. The runs that already read or wrote it keep
            their trace, and this cannot be undone.
          </p>
        </ConfirmDialog>
      )}
    </div>
  );
}
