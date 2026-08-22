import { useState } from "react";
import { useRead } from "../data/query";
import { Button } from "../ui/Button";
import { ProbabilityChart } from "./ProbabilityChart";
import type { History, PolymarketApi, TrackedEvent } from "./polymarketApi";
import { RANGES, rangeStart, reachesBeforeCoverage, type RangeChoice } from "./series";

/**
 * The series for one outcome of one event, with a range to choose and the boundary of what
 * was actually collected said in words beside the line that draws it.
 *
 * Said as well as drawn, deliberately: the line is where an operator sees the boundary
 * while reading the chart, and the sentence is where they see it when the requested range
 * reaches back past everything the archive holds — the case where there is barely a line
 * to look at (specs/terminal-polymarket).
 */

const EMPTY: History = { outcomeId: 0, points: [], collectedFrom: null, collectedTo: null };

export function OutcomeHistory({
  client,
  event,
}: {
  client: PolymarketApi;
  event: TrackedEvent;
}) {
  const outcomes = event.markets.flatMap((market) =>
    market.outcomes.map((outcome) => ({
      id: outcome.id,
      label: market.label === null ? outcome.name : `${market.label} · ${outcome.name}`,
    })),
  );

  const [outcomeId, setOutcomeId] = useState<number | null>(outcomes[0]?.id ?? null);
  const [range, setRange] = useState<RangeChoice>("30d");

  const history = useRead<History>({
    key: ["polymarket", "history", outcomeId, range],
    read: (signal) =>
      client.history(outcomeId!, signal, { since: rangeStart(range) }),
    initial: EMPTY,
    fallbackMessage: "the series could not be read",
    enabled: outcomeId !== null,
  });

  const selected = outcomes.find((outcome) => outcome.id === outcomeId) ?? null;
  const short = reachesBeforeCoverage(range, history.value.collectedFrom);

  return (
    <section className="flex flex-col gap-2 border-t border-border px-3 py-2">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <label className="flex items-center gap-1">
          <span className="text-ink-faint">Outcome</span>
          <select
            className="rounded border border-border bg-sunken px-1 py-0.5 text-ink"
            value={outcomeId ?? ""}
            onChange={(e) => setOutcomeId(Number(e.target.value))}
          >
            {outcomes.map((outcome) => (
              <option key={outcome.id} value={outcome.id}>
                {outcome.label}
              </option>
            ))}
          </select>
        </label>

        <div className="ml-auto flex items-center gap-1">
          {RANGES.map((choice) => (
            <Button
              key={choice}
              size="2xs"
              tone={range === choice ? "primary" : "quiet"}
              onClick={() => setRange(choice)}
            >
              {choice}
            </Button>
          ))}
        </div>
      </div>

      {history.error !== null ? (
        <p className="text-xs text-ink-faint">The series could not be read — {history.error}.</p>
      ) : (
        <ProbabilityChart history={history.value} label={selected?.label ?? ""} />
      )}

      {short && history.value.collectedFrom !== null && (
        <p className="text-xs text-warning">
          Collected only from {history.value.collectedFrom.toLocaleDateString()}. There is
          nothing before that and there cannot be — the provider does not give back a
          resolved market's history, and reaches only so far for the rest.
        </p>
      )}
    </section>
  );
}
