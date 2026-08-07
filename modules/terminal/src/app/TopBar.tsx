import { useSyncExternalStore } from "react";
import { sourceStore, type SourceId } from "../data/sourceStore";
import { useSourceHealth } from "./useSourceHealth";

const HEALTH_LABEL: Record<ReturnType<typeof useSourceHealth>, string> = {
  checking: "checking…",
  reachable: "connected",
  unreachable: "unreachable",
};

const HEALTH_DOT: Record<ReturnType<typeof useSourceHealth>, string> = {
  checking: "bg-ink-muted",
  reachable: "bg-up",
  unreachable: "bg-down",
};

export function TopBar() {
  const source = useSyncExternalStore(sourceStore.subscribe, sourceStore.getSnapshot);
  const sourceId = useSyncExternalStore(sourceStore.subscribe, sourceStore.getSourceId);
  const health = useSourceHealth(source);

  return (
    <header className="flex h-12 shrink-0 items-center gap-4 border-b border-border bg-panel px-4">
      <span className="text-sm font-semibold text-ink">TradingCenter · Terminal</span>

      <div className="ml-auto flex items-center gap-4">
        <label className="flex items-center gap-2 text-sm text-ink-muted">
          Source
          <select
            value={sourceId}
            onChange={(e) => sourceStore.setSource(e.target.value as SourceId)}
            className="rounded border border-border bg-panel-strong px-2 py-1 text-ink"
          >
            <option value="mock">mock</option>
            <option value="gateway">gateway</option>
          </select>
        </label>

        <span className="flex items-center gap-2 text-sm text-ink-muted">
          <span className={`h-2 w-2 rounded-full ${HEALTH_DOT[health]}`} aria-hidden />
          {sourceId} {HEALTH_LABEL[health]}
        </span>
      </div>
    </header>
  );
}
