import { Button } from "../ui/Button";
import { NO_RUN_FILTER, runFilterActive, timeframesOf, type RunFilter } from "./order";
import { interval } from "./present";
import type { StrategyItem } from "./strategiesApi";

const input = "rounded border border-border bg-sunken px-2 py-1 text-xs text-ink placeholder:text-ink-faint";

/** The filters above the runs. With one strategy picked its name and interval are already decided, so only the range
 *  and the results are offered. */
export function RunFilters({
  filter,
  onChange,
  strategies,
  ofOneStrategy,
  shown,
  total,
}: {
  filter: RunFilter;
  onChange(filter: RunFilter): void;
  strategies: readonly StrategyItem[];
  ofOneStrategy: boolean;
  shown: number;
  total: number;
}) {
  const set = (key: keyof RunFilter) => (e: { target: { value: string } }) => onChange({ ...filter, [key]: e.target.value });
  const minimum = (key: keyof RunFilter, label: string, placeholder: string) => (
    <label className="flex items-center gap-1">
      {label} ≥
      <input type="text" inputMode="decimal" aria-label={`${label} co najmniej`} className={`${input} w-16`} placeholder={placeholder} value={filter[key]} onChange={set(key)} />
    </label>
  );
  return (
    <div role="search" aria-label="Filtry uruchomień" className="flex flex-wrap items-center gap-x-3 gap-y-2 text-xs text-ink-muted">
      {!ofOneStrategy && (
        <>
          <input type="search" aria-label="szukaj w nazwach strategii" placeholder="szukaj w nazwach strategii" className={`${input} w-56`} value={filter.name} onChange={set("name")} />
          <select aria-label="Interwał" className={input} value={filter.timeframe} onChange={set("timeframe")}>
            <option value="">każdy interwał</option>
            {timeframesOf(strategies).map((tf) => (
              <option key={tf} value={tf}>
                {interval(tf)}
              </option>
            ))}
          </select>
        </>
      )}
      <label className="flex items-center gap-1" title="zakres backtestu mieści się w tych dniach">
        Zakres od
        <input type="date" aria-label="Zakres od" className={input} value={filter.from} onChange={set("from")} />
        do
        <input type="date" aria-label="Zakres do" className={input} value={filter.to} onChange={set("to")} />
      </label>
      {minimum("minTrades", "Transakcje", "0")}
      {minimum("minAnnualReturnPct", "Rocznie %", "0")}
      {minimum("minSharpe", "Sharpe", "0")}
      {runFilterActive(filter) && (
        <>
          <span className="tabular-nums">
            {shown} z {total}
          </span>
          <Button size="2xs" tone="muted" onClick={() => onChange(NO_RUN_FILTER)}>
            Wyczyść filtry
          </Button>
        </>
      )}
    </div>
  );
}
