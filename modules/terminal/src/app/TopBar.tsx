import { marketData } from "../data/marketData";
import type { SourcePart } from "../data/source";
import { useSourceHealth, type SourceHealth } from "./useSourceHealth";

const HEALTH_LABEL: Record<SourceHealth, string> = {
  checking: "checking…",
  reachable: "connected",
  unreachable: "unreachable",
};

const HEALTH_DOT: Record<SourceHealth, string> = {
  checking: "bg-ink-muted",
  reachable: "bg-up",
  unreachable: "bg-down",
};

export function TopBar() {
  const health = useSourceHealth(marketData.parts);

  return (
    <header className="flex h-12 shrink-0 items-center gap-4 border-b border-border bg-panel px-4">
      <span className="text-sm font-semibold text-ink">TradingCenter · Terminal</span>

      {/* One indicator per back end rather than one for "the source". They go
          down separately and the consequences differ: no archive means no
          candles anywhere, while no gateway means the instrument search stops
          and the charts carry on. An operator has to be able to tell which. */}
      <div className="ml-auto flex items-center gap-4 text-sm text-ink-muted">
        {marketData.parts.map((part) => (
          <PartHealth key={part.id} part={part} health={health[part.id] ?? "checking"} />
        ))}
      </div>
    </header>
  );
}

function PartHealth({ part, health }: { part: SourcePart; health: SourceHealth }) {
  return (
    <span className="flex items-center gap-2">
      <span className={`h-2 w-2 rounded-full ${HEALTH_DOT[health]}`} aria-hidden />
      <span>
        {part.label} {HEALTH_LABEL[health]}
      </span>
      {health === "unreachable" && (
        // Silence on the feed has to look different from a flat market, and an
        // operator needs to know what has stopped — naming the casualty rather
        // than declaring the whole terminal offline.
        <span className="text-down">— {part.whenUnreachable}</span>
      )}
    </span>
  );
}
