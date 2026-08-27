import type { WindowChange } from "./polymarketApi";
import { formatChange } from "./probability";

/**
 * A window is a move or a **named absence**, never a zero: a zero is a claim about the market where the truth is a
 * claim about the archive. The base point's moment is shown, because the provider's spacing wobbles.
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
