import { formatInstant } from "../ui/formatTime";
import { groupStrategies, trials } from "./order";
import { interval } from "./present";
import type { StrategyItem } from "./strategiesApi";

const changed = (d: Date) => formatInstant(d.getTime() / 1000).slice(0, 16);

/** Every strategy grouped by instrument and interval: a grid of cards over the whole tab while none is open, a narrow
 *  column beside the editor once one is. */
export function StrategyList({
  strategies,
  query,
  openId,
  wide,
  onOpen,
}: {
  strategies: readonly StrategyItem[];
  query: string;
  openId: number | null;
  wide: boolean;
  onOpen(id: number): void;
}) {
  const groups = groupStrategies(strategies, query);
  if (groups.length === 0 && strategies.length > 0) {
    return <p className="text-xs text-ink-muted">Żadna nazwa nie pasuje do „{query}”.</p>;
  }
  return (
    <div className={wide ? "space-y-5" : "space-y-3"}>
      {groups.map((group) => (
        <section key={group.key} aria-label={`${group.symbol} ${interval(group.timeframe)}`}>
          <h2 className="mb-1.5 flex items-baseline gap-2 border-b border-border pb-1 text-xs font-semibold tracking-wide text-secondary-strong uppercase">
            {group.symbol} · {interval(group.timeframe)}
            <span className="font-normal text-ink-faint normal-case">{group.strategies.length}</span>
          </h2>
          <ul className={wide ? "grid grid-cols-[repeat(auto-fill,minmax(18rem,1fr))] gap-2" : "space-y-0.5"}>
            {group.strategies.map(({ item, shortName }) => {
              const open = item.id === openId;
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    title={item.name}
                    onClick={() => onOpen(item.id)}
                    className={
                      wide
                        ? "flex h-full w-full flex-col gap-2 rounded border border-border bg-panel p-3 text-left transition-colors hover:border-primary-line hover:bg-panel-strong"
                        : `w-full rounded border-l-2 px-2 py-1.5 text-left ${open ? "border-primary bg-panel-strong" : "border-transparent hover:bg-panel"}`
                    }
                  >
                    <span className={`block text-ink ${wide ? "text-sm font-medium" : "line-clamp-2 text-xs font-medium"}`}>{shortName}</span>
                    <span className="mt-auto flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-ink-muted">
                      {wide && (
                        <span className="rounded bg-secondary-soft px-1.5 py-px font-medium text-secondary-strong">
                          {item.symbol} · {interval(item.timeframe)}
                        </span>
                      )}
                      <span>rew. {item.latestRevision}</span>
                      <span className={item.latestAuthor === "agent" ? "text-ink-muted" : "text-primary"}>
                        {item.latestAuthor === "agent" ? "agent" : "operator"}
                      </span>
                      <span className={item.trials === 0 ? "text-ink-faint" : "text-ink-secondary"}>{trials(item.trials)}</span>
                      {wide && <span className="ml-auto text-ink-faint tabular-nums">{changed(item.changedAt)}</span>}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}
