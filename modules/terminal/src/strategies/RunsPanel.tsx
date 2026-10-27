import { useState, type CSSProperties, type ReactNode } from "react";
import { Button } from "../ui/Button";
import { formatInstant } from "../ui/formatTime";
import { nextSort, sortRuns, type RunSort, type RunSortKey } from "./order";
import { num, pct, r, STATUS_LABEL, WITHOUT_COSTS_NOTE } from "./present";
import type { RunItem } from "./strategiesApi";

const day = (d: Date) => formatInstant(d.getTime() / 1000).slice(0, 10);
const inProgress = (run: RunItem) => run.status === "queued" || run.status === "running";

/** A table where the panel is wide and a card per run where it is not — measured on the panel, not the screen, because
 *  the tab can sit beside the agent's panel on a wide monitor. One grid template for the header and every row, in three
 *  widths: `compact` folds revision, range and who asked into one cell, `full` gives each its column, `r` adds R. */
function columns(width: "compact" | "full" | "r", named: boolean, selectable: boolean): string {
  const compact = width === "compact";
  return [
    selectable && "1.25rem",
    "2.5rem",
    named && "minmax(8rem, 1fr)",
    compact ? "4.5rem" : "6rem",
    ...(compact
      ? [!named && "minmax(8rem, 1fr)"]
      : ["2rem", named ? "10.5rem" : "minmax(10.5rem, 1fr)", "4rem"]),
    "4.75rem",
    "4.5rem",
    "4.5rem",
    ...(width === "r" ? ["4.5rem", "5.5rem", "5.5rem"] : []),
    "3.5rem",
    compact ? "3.5rem" : "4rem",
  ]
    .filter(Boolean)
    .join(" ");
}

/** What a card can be ordered by — the columns a narrow panel has no header for. */
const CARD_SORTS: [RunSortKey, string][] = [
  ["annualReturnPct", "zwrot roczny"],
  ["returnPct", "zwrot"],
  ["sharpe", "Sharpe"],
  ["trades", "transakcje"],
  ["from", "początek zakresu"],
  ["strategy", "strategia"],
  ["status", "stan"],
];

/** A header that orders the rows by its column; `aria-sort` says which way. */
function SortHeader({
  column,
  sort,
  onSort,
  className = "",
  children,
}: {
  column: RunSortKey;
  sort: RunSort | null;
  onSort(column: RunSortKey): void;
  className?: string;
  children: ReactNode;
}) {
  const on = sort?.key === column;
  return (
    <span role="columnheader" aria-sort={on ? (sort.descending ? "descending" : "ascending") : "none"} className={className}>
      <button
        type="button"
        onClick={() => onSort(column)}
        className={`inline-flex items-center gap-0.5 hover:text-ink ${on ? "text-primary" : ""}`}
      >
        {children}
        <span aria-hidden className={on ? "" : "invisible"}>
          {sort?.descending === false && on ? "▲" : "▼"}
        </span>
      </button>
    </span>
  );
}

/** Runs, newest first until a header orders them — which of them the agent asked for included. With `strategyNames`,
 *  of several strategies. */
export function RunsPanel({
  runs,
  error,
  picked,
  onPick,
  onCancel,
  strategyNames,
  selected,
  onSelect,
}: {
  runs: readonly RunItem[];
  error: string | null;
  picked: number | null;
  onPick(id: number): void;
  /** Given, the list is of every strategy and names each run's. */
  strategyNames?: ReadonlyMap<number, string>;
  /** Says its own failure; the list only asks. */
  onCancel(id: number): Promise<void>;
  /** Given, every run not in progress can be ticked — one selection, for comparing and for deleting alike. */
  selected?: ReadonlySet<number>;
  onSelect?(id: number): void;
}) {
  const [sort, setSort] = useState<RunSort | null>(null);
  if (runs.length === 0) {
    return (
      <p className="text-sm text-ink-muted">
        {error ?? (strategyNames ? "Nie było jeszcze uruchomień." : "Ta strategia nie miała jeszcze uruchomień.")}
      </p>
    );
  }
  // A strategy without a stop has no R: three columns of dashes say nothing a missing column does not.
  const inR = runs.some((run) => run.headline?.totalR != null);
  const named = strategyNames !== undefined;
  const selectable = onSelect !== undefined;
  // The three R columns join only where there is room for them; below that width R is in the report alone.
  const grid = {
    "--runs-cols-compact": columns("compact", named, selectable),
    "--runs-cols": columns("full", named, selectable),
    "--runs-cols-r": columns(inR ? "r" : "full", named, selectable),
  } as CSSProperties;
  // On a card the box stands alone in the first column and everything after the title line starts beside it.
  const card = selectable ? "grid-cols-[1.25rem_minmax(0,1fr)_auto]" : "grid-cols-[minmax(0,1fr)_auto]";
  const below = selectable ? "col-span-2 col-start-2" : "col-span-2";
  const row = `grid ${card} items-baseline gap-x-2 gap-y-0.5 @2xl:[grid-template-columns:var(--runs-cols-compact)] @5xl:[grid-template-columns:var(--runs-cols)] @7xl:[grid-template-columns:var(--runs-cols-r)] @5xl:gap-x-3`;
  // In the compact table revision, range and who asked are a line under the name and the status; without names, a column.
  const meta = named
    ? `@2xl:row-start-2 ${selectable ? "@2xl:col-[3/span_2]" : "@2xl:col-[2/span_2]"}`
    : "@2xl:col-auto";
  const right = "text-right tabular-nums";
  const sorted = sortRuns(runs, sort, strategyNames);
  const sortBy = (column: RunSortKey) => setSort((was) => nextSort(was, column));
  const header = (column: RunSortKey, label: string, className = "") => (
    <SortHeader column={column} sort={sort} onSort={sortBy} className={className}>
      {label}
    </SortHeader>
  );

  return (
    <div className="@container text-xs">
      <div className="mb-2 flex items-center gap-2 text-ink-muted @2xl:hidden">
        <label className="flex items-center gap-2">
          Sortuj
          <select
            aria-label="Sortuj uruchomienia"
            className="rounded border border-border bg-sunken px-2 py-1 text-xs text-ink"
            value={sort?.key ?? ""}
            onChange={(e) => setSort(e.target.value === "" ? null : nextSort(null, e.target.value as RunSortKey))}
          >
            <option value="">od najnowszego</option>
            {CARD_SORTS.filter(([key]) => named || key !== "strategy").map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
        {sort && (
          <button
            type="button"
            aria-label={sort.descending ? "Malejąco — odwróć" : "Rosnąco — odwróć"}
            className="rounded border border-border px-1.5 py-0.5 hover:text-ink"
            onClick={() => sortBy(sort.key)}
          >
            {sort.descending ? "▼" : "▲"}
          </button>
        )}
      </div>
    <div role="table" aria-label="Uruchomienia" className="overflow-x-auto" style={grid}>
      <div>
      <div role="rowgroup" className="hidden @2xl:block">
        <div role="row" className={`${row} border-b border-border px-2 pb-1 text-left text-ink-muted`}>
          {onSelect && <span role="columnheader" aria-label="Zaznaczenie" />}
          {header("id", "#")}
          {named && header("strategy", "Strategia")}
          {header("status", "Stan")}
          {header("revision", "Rew.", "hidden @5xl:block")}
          {header("from", "Zakres", named ? "hidden @5xl:block" : "")}
          {header("requestedBy", "Zlecił", "hidden @5xl:block")}
          {header("trades", "Transakcje", right)}
          {header("returnPct", "Zwrot", right)}
          {header("annualReturnPct", "Rocznie", right)}
          {inR && (
            <>
              {header("totalR", "Suma", `${right} hidden @7xl:block`)}
              {header("expectancyR", "Oczekiwana", `${right} hidden @7xl:block`)}
              {header("maxDrawdownR", "Obsunięcie", `${right} hidden @7xl:block`)}
            </>
          )}
          {header("sharpe", "Sharpe", right)}
          <span role="columnheader" />
        </div>
      </div>
      <div role="rowgroup">
        {sorted.map((run) => {
          const done = run.status === "done";
          // [label, value, shown on a card, the class that places it in the table]
          const metrics: [string, string, boolean, string][] = [
            ["Transakcje", num(run.headline?.trades), true, "@2xl:block"],
            ["Zwrot", pct(run.headline?.returnPct), true, "@2xl:block"],
            ["Rocznie", pct(run.headline?.annualReturnPct), true, "@2xl:block"],
            ...(inR
              ? ([
                  ["Suma", r(run.headline?.totalR), run.headline?.totalR != null, "@2xl:hidden @7xl:block"],
                  ["Oczekiwana", r(run.headline?.expectancyR), run.headline?.expectancyR != null, "@2xl:hidden @7xl:block"],
                  ["Obsunięcie", r(run.headline?.maxDrawdownR), run.headline?.maxDrawdownR != null, "@2xl:hidden @7xl:block"],
                ] as [string, string, boolean, string][])
              : []),
            ["Sharpe", num(run.headline?.sharpe), true, "@2xl:block"],
          ];
          return (
            <div
              role="row"
              key={run.id}
              onClick={() => done && onPick(run.id)}
              className={`${row} border-b border-border px-2 py-2 @2xl:py-1.5 ${done ? "cursor-pointer hover:bg-panel" : ""} ${picked === run.id ? "bg-panel-strong" : ""}`}
            >
              {onSelect && (
                <span role="cell" onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    aria-label={`Zaznacz uruchomienie ${run.id}`}
                    className="h-3.5 w-3.5 cursor-pointer accent-[var(--color-primary)] disabled:cursor-not-allowed disabled:opacity-30"
                    disabled={inProgress(run)}
                    checked={selected?.has(run.id) ?? false}
                    onChange={() => onSelect(run.id)}
                  />
                </span>
              )}
              {/* One line on a card — number and name — and two columns of the table. */}
              <span className="flex min-w-0 gap-2 @2xl:contents">
                <span role="cell" className="shrink-0 text-ink-muted tabular-nums">
                  #{run.id}
                </span>
                {named && (
                  <span role="cell" className="truncate text-ink" title={strategyNames.get(run.strategyId)}>
                    {strategyNames.get(run.strategyId) ?? `#${run.strategyId}`}
                  </span>
                )}
              </span>
              <span
                role="cell"
                className={`truncate text-right @2xl:text-left ${run.status === "failed" ? "text-critical" : "text-ink-secondary"}`}
                title={run.reason ?? undefined}
              >
                {STATUS_LABEL[run.status] ?? run.status}
                {run.headline?.withoutCosts && (
                  <span title={WITHOUT_COSTS_NOTE} className="ml-1 rounded bg-warning-soft px-1 text-warning">
                    bez kosztów
                  </span>
                )}
              </span>
              <span className={`${below} ${meta} flex flex-wrap gap-x-2 text-ink-muted @5xl:contents`}>
                <span role="cell" className="tabular-nums">
                  <span className="@5xl:hidden">rew. </span>
                  {run.revision}
                </span>
                <span role="cell" className="whitespace-nowrap tabular-nums @2xl:order-first @5xl:order-none">
                  {day(run.from)} – {day(run.to)}
                </span>
                <span role="cell">{run.requestedBy === "agent" ? "agent" : "operator"}</span>
              </span>
              {/* A card says nothing of a run that has no numbers yet; the table keeps its columns. */}
              <span className={`${below} ${run.headline ? "flex" : "hidden"} flex-wrap gap-x-3 @2xl:contents`}>
                {metrics.map(([label, value, shown, placed]) => (
                  <span role="cell" key={label} className={`${right} ${shown ? "" : "hidden"} ${placed}`}>
                    <span className="mr-1 text-ink-muted @2xl:hidden">{label}</span>
                    <span className="text-ink">{value}</span>
                  </span>
                ))}
              </span>
              <span role="cell" className={`${below} text-right empty:hidden @2xl:col-auto @2xl:empty:block`}>
                {inProgress(run) && (
                  <Button
                    size="2xs"
                    tone="muted"
                    onClick={(e) => {
                      e.stopPropagation();
                      void onCancel(run.id);
                    }}
                  >
                    Anuluj
                  </Button>
                )}
              </span>
              {run.status === "failed" && run.reason && (
                // The reason is too long for a cell: a line of its own under the row, cut with the whole on hover.
                <span className={`${below} truncate text-critical ${selectable ? "@2xl:col-[2/-1]" : "@2xl:col-span-full"}`} title={run.reason}>
                  {run.reason}
                </span>
              )}
            </div>
          );
        })}
      </div>
      </div>
    </div>
    </div>
  );
}
