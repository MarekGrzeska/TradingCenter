import { useState } from "react";
import { messageOf, useRead } from "../data/query";
import { Button } from "../ui/Button";
import { formatInstant } from "../ui/formatTime";
import type { Change, RevisionEntry, StrategiesApi } from "./strategiesApi";


function shown(value: unknown): string {
  return value === null || value === undefined ? "—" : typeof value === "string" ? value : JSON.stringify(value);
}

/**
 * Every revision of the open strategy, and what each changed against the one before it, by path. An older one is put back
 * by saving its content as the next revision — nothing that was saved is ever changed (`terminal-strategies`).
 */
export function HistoryPanel({
  api,
  strategyId,
  latest,
  onRestore,
}: {
  api: StrategiesApi;
  strategyId: number;
  latest: number;
  onRestore(n: number): Promise<void>;
}) {
  const [picked, setPicked] = useState<number>(latest);
  const [failure, setFailure] = useState<string | null>(null);
  const revisions = useRead<RevisionEntry[]>({
    key: ["strategies", strategyId, "revisions", latest],
    read: (s) => api.revisions(strategyId, s),
    initial: [],
    fallbackMessage: "nie udało się wczytać historii",
  });
  const changes = useRead<Change[]>({
    key: ["strategies", strategyId, "changes", picked],
    read: (s) => api.changes(strategyId, picked, s),
    initial: [],
    fallbackMessage: "nie udało się wczytać zmian",
  });

  return (
    <div className="grid min-h-0 grid-cols-[14rem_1fr] gap-3">
      <ol aria-label="Rewizje" className="space-y-1">
        {revisions.value.map((r) => (
          <li key={r.n}>
            <button
              type="button"
              onClick={() => setPicked(r.n)}
              className={`w-full rounded px-2 py-1 text-left text-xs ${r.n === picked ? "bg-panel-strong text-ink" : "text-ink-secondary hover:bg-panel"}`}
            >
              <span className="font-semibold">rewizja {r.n}</span> · {r.author === "agent" ? "agent" : "operator"}
              <br />
              <span className="text-ink-faint">{formatInstant(r.createdAt.getTime() / 1000)}</span>
            </button>
          </li>
        ))}
      </ol>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-ink">Zmiany w rewizji {picked}</h3>
          {picked !== latest && (
            <Button
              size="xs"
              onClick={() => {
                setFailure(null);
                onRestore(picked).catch((cause: unknown) => setFailure(messageOf(cause, "nie udało się przywrócić rewizji")));
              }}
            >
              Przywróć jako nową rewizję
            </Button>
          )}
        </div>
        {failure !== null && <p role="alert" className="text-sm text-critical">{failure}</p>}
        {picked === 1 ? (
          <p className="mt-2 text-sm text-ink-muted">Pierwsza rewizja — nie ma z czym jej porównać.</p>
        ) : changes.value.length === 0 ? (
          <p className="mt-2 text-sm text-ink-muted">Brak zmian względem poprzedniej rewizji.</p>
        ) : (
          <table className="mt-2 w-full table-fixed text-xs">
            <thead className="text-left text-ink-muted">
              <tr>
                <th className="w-48 py-1">Ścieżka</th>
                <th className="py-1">Przed</th>
                <th className="py-1">Po</th>
              </tr>
            </thead>
            <tbody>
              {changes.value.map((c) => (
                <tr key={c.path} className="border-t border-border align-top">
                  <td className="py-1 font-mono text-ink">{c.path}</td>
                  <td className="break-words py-1 font-mono text-down">{c.kind === "added" ? "—" : shown(c.before)}</td>
                  <td className="break-words py-1 font-mono text-up">{c.kind === "removed" ? "—" : shown(c.after)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
