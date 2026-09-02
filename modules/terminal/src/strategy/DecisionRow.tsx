import { formatBar, formatLevel, KIND_LABEL, KIND_TONE } from "./decisionFormat";
import type { Decision } from "./strategyApi";

/**
 * **The revision travels with the row** — today's rule beside last week's decision answers convincingly and wrongly.
 * The kind of refusal is a badge; why is in `decisionFormat.ts`, which the dialog shares.
 */

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
      className={`${isTrade ? "decision decision-trade" : "decision"}${onOpen === undefined ? "" : " decision-openable"}`}
      onClick={onOpen === undefined ? undefined : () => onOpen(decision)}
      title={onOpen === undefined ? undefined : "otwórz: odczyty, parametry, cechy"}
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
