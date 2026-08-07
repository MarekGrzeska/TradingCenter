import { marketData } from "../data/marketData";
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
  const health = useSourceHealth(marketData);

  return (
    <header className="flex h-12 shrink-0 items-center gap-4 border-b border-border bg-panel px-4">
      <span className="text-sm font-semibold text-ink">TradingCenter · Terminal</span>

      <div className="ml-auto flex items-center gap-2 text-sm text-ink-muted">
        <span className={`h-2 w-2 rounded-full ${HEALTH_DOT[health]}`} aria-hidden />
        <span>capital-gateway {HEALTH_LABEL[health]}</span>
        {health === "unreachable" && (
          // Silence on the feed has to look different from a flat market, and
          // an operator needs to know the data on screen has stopped moving.
          <span className="text-down">— data on screen is stale</span>
        )}
      </div>
    </header>
  );
}
