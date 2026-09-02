import { useRead } from "../data/query";
import { ModalShell } from "../ui/ModalShell";
import { UnreachableNotice } from "../ui/UnreachableNotice";
import { formatBar, formatLevel, KIND_LABEL, KIND_TONE } from "./decisionFormat";
import { latestCandles, latestReadings, readSnapshot } from "./readings";
import type { Decision, DecisionDetail, ParameterSet, StrategyApi } from "./strategyApi";

/**
 * A decision read down to what it stood on: the readings the platform snapshotted, not what the archive shows today,
 * and the parameter set it was computed with, by version. **Nothing here is an action** — a setup is a reading.
 */

/** How many bars back the readings table shows. Enough for a crossing (two) and its run-up. */
const BARS_SHOWN = 5;

const NO_SETS: ParameterSet[] = [];

function formatNumber(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "—";
  return Math.abs(value) >= 100 ? value.toFixed(2) : value.toFixed(4);
}

export function DecisionDialog({
  client,
  decision,
  onClose,
}: {
  client: StrategyApi;
  decision: Decision;
  onClose(): void;
}) {
  const detail = useRead<DecisionDetail | null>({
    key: ["strategy", "decision", decision.id],
    read: (signal) => client.readDecision(decision.id, signal),
    initial: null,
    fallbackMessage: "nie udało się odczytać decyzji",
  });

  // The whole strategy's sets rather than one by id: the contract lists them, and one call
  // answers every decision of this strategy the operator opens next.
  const sets = useRead<ParameterSet[]>({
    key: ["strategy", "parameter-sets", decision.strategyId],
    read: (signal) => client.listParameterSets(signal, decision.strategyId),
    initial: NO_SETS,
    fallbackMessage: "nie udało się odczytać zestawów parametrów",
  });

  const parameterSet = sets.value.find((one) => one.id === decision.parameterSetId) ?? null;
  const isTrade = decision.action === "trade";
  const kind = decision.reasonKind;
  const snapshot = detail.value === null ? null : readSnapshot(detail.value.facts);
  const features = Object.entries(detail.value?.features ?? decision.features);

  return (
    <ModalShell
      title={`${decision.symbol} · ${formatBar(decision.asOf)}`}
      size="wide"
      showCloseButton
      onClose={onClose}
    >
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto text-xs">
        <section className="flex flex-wrap items-baseline gap-3" data-testid="decision-verdict">
          {isTrade ? (
            <span className="badge badge-trade">{decision.direction === "short" ? "short" : "long"}</span>
          ) : (
            <span className={`badge ${kind === null ? "kind-ordinary" : KIND_TONE[kind]}`}>
              {kind === null ? "odmowa" : KIND_LABEL[kind]}
            </span>
          )}
          <span className="text-ink">{decision.reason ?? "bez podanego powodu"}</span>
          <span className="ml-auto text-ink-faint">
            {decision.strategyId}
            {decision.strategyRevision === null
              ? " · kod w obrazie"
              : ` · reguła @${decision.strategyRevision}`}
          </span>
        </section>

        <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <dl className="detail-list" data-testid="decision-levels">
            <dt>poziomy</dt>
            {isTrade ? (
              <>
                <dd>wejście {formatLevel(decision.entry)}</dd>
                <dd>obrona {formatLevel(decision.stop)}</dd>
                <dd>cel {formatLevel(decision.target)}</dd>
                <dd>{decision.rr === null ? "R —" : `${decision.rr.toFixed(2)}R`}</dd>
                {decision.score !== null && <dd>score {decision.score.toFixed(2)}</dd>}
              </>
            ) : (
              <dd className="text-ink-faint">odmowa nie ma poziomów</dd>
            )}
          </dl>

          <dl className="detail-list" data-testid="decision-parameters">
            <dt>parametry</dt>
            {/* The version, not only the values: two sets with the same numbers are still two
                sets, and the one that decided this is a fact about the decision. */}
            <dd>
              zestaw #{decision.parameterSetId}
              {parameterSet !== null && ` · v${parameterSet.version}`}
            </dd>
            {parameterSet === null
              ? sets.status === "ready" && <dd className="text-ink-faint">wartości nieodczytane</dd>
              : Object.entries(parameterSet.params).map(([name, value]) => (
                  <dd key={name}>
                    {name} = {value}
                  </dd>
                ))}
          </dl>

          <dl className="detail-list md:col-span-2" data-testid="decision-features">
            <dt>cechy, które strategia zmierzyła</dt>
            {features.length === 0 ? (
              <dd className="text-ink-faint">żadnej</dd>
            ) : (
              features.map(([name, value]) => (
                <dd key={name}>
                  {name} = {formatNumber(value)}
                </dd>
              ))
            )}
          </dl>
        </section>

        {detail.error !== null && (
          <UnreachableNotice onRetry={detail.reload}>{detail.error}</UnreachableNotice>
        )}
        {detail.status === "loading" && <p className="text-ink-faint">Czytam odczyty…</p>}

        {snapshot !== null && (
          <section className="flex flex-col gap-3" data-testid="decision-readings">
            <h3 className="text-xs font-semibold text-ink-secondary">
              odczyty, na których decyzja stanęła
              <span className="ml-2 font-normal text-ink-faint">
                zapis z chwili decyzji, nie stan archiwum dziś · 0 to świeca decyzji
              </span>
            </h3>

            {snapshot.values.length === 0 && snapshot.candles.length === 0 && (
              <p className="text-ink-faint">
                Zapis nie niesie odczytów — tak wygląda decyzja, dla której faktów nie dało
                się przeczytać.
              </p>
            )}

            {snapshot.values.map((fact) => {
              const lines = Object.keys(fact.lines);
              const rows = latestReadings(fact, BARS_SHOWN);
              return (
                <table key={fact.key} className="readings">
                  <caption>
                    {fact.key}
                    <span className="ml-2 text-ink-faint">{fact.resolution}</span>
                  </caption>
                  <thead>
                    <tr>
                      <th>−</th>
                      <th>świeca</th>
                      {lines.map((line) => (
                        <th key={line}>{line}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.offset}>
                        <td>{row.offset}</td>
                        <td>{formatBar(new Date(row.time))}</td>
                        {lines.map((line) => (
                          <td key={line}>{formatNumber(row.values[line])}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              );
            })}

            {snapshot.candles.length > 0 && (
              <table className="readings">
                <caption>świece</caption>
                <thead>
                  <tr>
                    <th>−</th>
                    <th>świeca</th>
                    <th>open</th>
                    <th>high</th>
                    <th>low</th>
                    <th>close</th>
                  </tr>
                </thead>
                <tbody>
                  {latestCandles(snapshot.candles, BARS_SHOWN).map((candle, offset) => (
                    <tr key={candle.time}>
                      <td>{offset}</td>
                      <td>{formatBar(new Date(candle.time))}</td>
                      <td>{formatNumber(candle.open)}</td>
                      <td>{formatNumber(candle.high)}</td>
                      <td>{formatNumber(candle.low)}</td>
                      <td>{formatNumber(candle.close)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        )}
      </div>
    </ModalShell>
  );
}
