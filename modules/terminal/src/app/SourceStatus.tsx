import { identity } from "../data/marketData";
import { marketData } from "../data/marketData";
import type { SourcePart } from "../data/source";
import { useIdentityState } from "./useIdentityState";
import { useSourceHealth, type SourceHealth } from "./useSourceHealth";
import { AccountMenu } from "./AccountMenu";

const HEALTH_LABEL: Record<SourceHealth, string> = {
  checking: "checking…",
  reachable: "connected",
  unreachable: "unreachable",
  "signed-out": "needs sign-in",
};

// Chrome status, not market direction: these used to borrow `up` and `down`, which made a reachable back
// end the same teal as a rising candle. `good`/`critical` say nothing about a price.
const HEALTH_DOT: Record<SourceHealth, string> = {
  checking: "bg-ink-muted",
  reachable: "bg-good",
  unreachable: "bg-critical",
  // Amber, not red: nothing here is broken. The back end is fine and does not know who is asking, and a
  // red dot on it is a claim about Azure the terminal has no evidence for.
  "signed-out": "bg-warning",
};

/** The chip a status sits in. Only a degraded one is filled — a healthy terminal is
 *  quiet, and three green chips in a row would draw the eye to the thing that needs no
 *  attention. */
const HEALTH_CHIP: Record<SourceHealth, string> = {
  checking: "border-transparent",
  reachable: "border-transparent",
  unreachable: "border-critical/40 bg-critical-soft text-ink-secondary",
  "signed-out": "border-warning/40 bg-warning-soft text-ink-secondary",
};

export function SourceStatus() {
  const health = useSourceHealth(marketData.parts);
  const signedIn = useIdentityState(identity);

  return (
    // One indicator per back end rather than one for "the source". They go down separately and the
    // consequences differ: no archive means no candles anywhere, while no gateway means the instrument
    // search stops and the charts carry on. An operator has to be able to tell which.
    <div className="mt-auto flex flex-col items-stretch gap-2 border-t border-border pt-3 text-xs text-ink-muted">
      {marketData.parts.map((part) => (
        <PartHealth key={part.id} part={part} health={health[part.id] ?? "checking"} />
      ))}
      <AccountMenu identity={identity} state={signedIn} />
    </div>
  );
}

function PartHealth({ part, health }: { part: SourcePart; health: SourceHealth }) {
  return (
    <span
      className={`flex flex-wrap items-center gap-x-2 rounded-lg border px-2 py-1 ${HEALTH_CHIP[health]}`}
    >
      <span className={`h-2 w-2 shrink-0 rounded-full ${HEALTH_DOT[health]}`} aria-hidden />
      <span>
        {part.label} {HEALTH_LABEL[health]}
      </span>
      {health === "unreachable" && (
        // Silence on the feed has to look different from a flat market, and an operator needs to know
        // what has stopped — naming the casualty rather than declaring the whole terminal offline.
        <span className="text-critical">— {part.whenUnreachable}</span>
      )}
    </span>
  );
}
