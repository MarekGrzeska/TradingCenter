import type { WindowChange } from "./polymarketApi";
import { formatChange } from "./probability";

/**
 * The seven windows for one outcome.
 *
 * The whole content of this component is the third state. A window is a move, or it is a
 * **named absence** — never a zero, because a zero is a claim about the market where the
 * truth is a claim about the archive (specs/terminal-polymarket, "Zmiana w oknie jest
 * liczona przez moduł i ma nazwany brak"). An empty cell would be the same lie told
 * quietly, so an unavailable window says "no coverage" and carries the module's reason in
 * its title.
 *
 * The base point's moment is shown for the windows that have one. The provider's spacing
 * wobbles and widens, so "24h" is measured against whatever point the archive actually
 * holds near that edge, and an operator comparing two rows deserves to see which.
 */
export function WindowChanges({ windows }: { windows: WindowChange[] }) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1">
      {windows.map((window) => (
        <li key={window.window} className="flex items-baseline gap-1">
          <span className="text-ink-faint">{window.window}</span>
          {window.change === null ? (
            <span
              className="text-ink-faint italic"
              title={window.unavailable ?? "the collected history does not reach back that far"}
            >
              no coverage
            </span>
          ) : (
            <span
              className={
                window.change > 0
                  ? "text-up"
                  : window.change < 0
                    ? "text-down"
                    : "text-ink"
              }
              title={
                window.baselineAt === null
                  ? undefined
                  : `measured against ${window.baselineAt.toISOString()}`
              }
            >
              {formatChange(window.change)}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}
