import { identity } from "../data/marketData";
import { marketData } from "../data/marketData";
import type { SourcePart } from "../data/source";
import { useIdentityState } from "./useIdentityState";
import { useSourceHealth, type SourceHealth } from "./useSourceHealth";
import { Button } from "../ui/Button";

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

export function TopBar() {
  const health = useSourceHealth(marketData.parts);
  const signedIn = useIdentityState(identity);

  return (
    <header className="flex h-12 shrink-0 items-center gap-4 border-b border-border bg-panel px-4">
      <span className="flex items-baseline gap-1.5 text-sm font-semibold">
        <span className="text-ink">TradingCenter</span>
        <span className="text-secondary">Terminal</span>
      </span>

      {/* One indicator per back end rather than one for "the source". They go
          down separately and the consequences differ: no archive means no
          candles anywhere, while no gateway means the instrument search stops
          and the charts carry on. An operator has to be able to tell which. */}
      <div className="ml-auto flex items-center gap-4 text-sm text-ink-muted">
        {/* Sign-in sits beside them and not among them, because it is not a back end — and it is the
            first thing to read when nothing is arriving. Absent entirely when no identity is configured. */}
        {signedIn !== "unconfigured" && <SignInState signedIn={signedIn === "signed-in"} />}
        {marketData.parts.map((part) => (
          <PartHealth key={part.id} part={part} health={health[part.id] ?? "checking"} />
        ))}
      </div>
    </header>
  );
}

function SignInState({ signedIn }: { signedIn: boolean }) {
  if (signedIn) {
    return (
      <span className="flex items-center gap-2 rounded-full px-2 py-0.5">
        <span className="h-2 w-2 rounded-full bg-good" aria-hidden />
        <span>signed in</span>
      </span>
    );
  }
  return (
    <span className="flex items-center gap-2 rounded-full border border-critical/40 bg-critical-soft px-2 py-0.5">
      <span className="h-2 w-2 rounded-full bg-critical" aria-hidden />
      <span className="text-critical">signed out</span>
      <Button
        tone="primary"
        size="xs"
        onClick={() => identity.signIn()}
      >
        Sign in
      </Button>
    </span>
  );
}

function PartHealth({ part, health }: { part: SourcePart; health: SourceHealth }) {
  return (
    <span
      className={`flex items-center gap-2 rounded-full border px-2 py-0.5 ${HEALTH_CHIP[health]}`}
    >
      <span className={`h-2 w-2 rounded-full ${HEALTH_DOT[health]}`} aria-hidden />
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
