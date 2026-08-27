import type { Decision, ReasonKind } from "./strategyApi";

/**
 * The kind of refusal is a badge because the three have three answers: fetch history, read the strategy, change the
 * limit. **The revision travels with the row** — today's rule beside last week's decision answers convincingly and wrongly.
 */

const KIND_LABEL: Record<ReasonKind, string> = {
  strategy: "strategia",
  coverage: "brak danych",
  limit: "limit",
};

/** `coverage` is the one that wants attention: it is answered by doing something to the
 *  archive. The other two are the system deciding, which is not a warning. */
const KIND_TONE: Record<ReasonKind, string> = {
  strategy: "kind-ordinary",
  coverage: "kind-missing",
  limit: "kind-limit",
};

function formatBar(at: Date): string {
  return at.toLocaleString(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Two decimal places and a sign, so a level lines up with the one above it. */
function formatLevel(value: number | null): string {
  return value === null ? "—" : value.toFixed(2);
}

export function DecisionRow({
  decision,
  onOpen,
}: {
  decision: Decision;
  onOpen?: (decision: Decision) => void;
}) {
  const isTrade = decision.action === "trade";
  const kind = decision.reasonKind;

  return (
    <tr
      className={isTrade ? "decision decision-trade" : "decision"}
      onClick={onOpen === undefined ? undefined : () => onOpen(decision)}
      data-testid="decision-row"
    >
      <td className="decision-bar">{formatBar(decision.asOf)}</td>
      <td className="decision-symbol">
        {decision.symbol}
        {decision.strategyRevision !== null && (
          <span className="ml-1 text-ink-faint" title="rewizja reguły, którą to policzono">
            @{decision.strategyRevision}
          </span>
        )}
      </td>
      <td className="decision-action">
        {isTrade ? (
          <span className="badge badge-trade">
            {decision.direction === "short" ? "short" : "long"}
          </span>
        ) : (
          // The badge carries the kind, not the word "no". What an operator needs to see
          // at a glance is *which* no it was.
          <span className={`badge ${kind === null ? "kind-ordinary" : KIND_TONE[kind]}`}>
            {kind === null ? "odmowa" : KIND_LABEL[kind]}
          </span>
        )}
      </td>
      <td className="decision-reason" title={decision.reason ?? undefined}>
        {decision.reason ?? "—"}
      </td>
      <td className="decision-levels">
        {isTrade ? `${formatLevel(decision.entry)} / ${formatLevel(decision.stop)}` : "—"}
      </td>
      <td className="decision-rr">{decision.rr === null ? "—" : `${decision.rr.toFixed(2)}R`}</td>
    </tr>
  );
}
