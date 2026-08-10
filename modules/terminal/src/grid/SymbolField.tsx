import { Link } from "react-router";
import type { PairsStatus } from "../instruments/useTrackedPairs";

/**
 * The only way a symbol reaches a slot: picked from what the archive is
 * actually collecting, never typed from memory — a chart for a pair nobody
 * archives has nothing to show (terminal-grid spec, "Slot przyjmuje wyłącznie
 * instrument archiwizowany").
 *
 * A plain select rather than a search field, because the list it offers is short
 * by construction — the archive's own ceiling on tracked pairs bounds it — and
 * making an operator type a phrase to see six instruments is work that buys
 * nothing. The list arrives from the grid, which reads `/pairs` once for every
 * slot; this field asks the archive nothing of its own.
 */
export function SymbolField({
  label,
  value,
  symbols,
  status,
  error,
  onRetry,
  onChange,
}: {
  label: string;
  value: string | null;
  /** Every archived symbol, already sorted. */
  symbols: readonly string[];
  status: PairsStatus;
  /** Why the list could not be read; shown only when there is no list at all. */
  error: string | null;
  onRetry(): void;
  onChange(symbol: string | null): void;
}) {
  // A failed read with nothing to offer is the only case that replaces the
  // picker: a list already on screen stays usable while a later poll fails,
  // and the slot keeps whatever is set in it either way.
  if (symbols.length === 0 && status === "unreachable") {
    return (
      <span className="flex items-center gap-2 text-xs text-ink-muted">
        {/* The slot keeps charting what it was set to; the header keeps saying
            what that is (terminal-grid spec, "Listy archiwizowanych nie da się
            odczytać"). */}
        {value !== null && <span className="text-sm font-semibold text-ink">{value}</span>}
        <span>Can’t pick an instrument — {error ?? "the archive is not answering"}.</span>
        <button
          type="button"
          onClick={onRetry}
          className="rounded border border-border px-1.5 py-0.5 text-xs text-ink hover:bg-panel-strong"
        >
          Retry
        </button>
      </span>
    );
  }

  if (symbols.length === 0 && status === "ready") {
    return (
      <span className="text-xs text-ink-muted">
        Nothing is archived yet — add instruments in the{" "}
        <Link to="/instruments" className="text-ink underline">
          Instruments
        </Link>{" "}
        tab.
      </span>
    );
  }

  // A remembered symbol the list does not carry still belongs in the select, or
  // the field would silently show a different instrument than the slot charts.
  const options = value !== null && !symbols.includes(value) ? [value, ...symbols] : symbols;

  return (
    <select
      aria-label={label}
      value={value ?? ""}
      onChange={(event) => onChange(event.target.value === "" ? null : event.target.value)}
      className="rounded border border-border bg-panel-strong px-1.5 py-0.5 text-sm font-semibold text-ink"
    >
      <option value="">{status === "loading" ? "Loading…" : "Symbol…"}</option>
      {options.map((symbol) => (
        <option key={symbol} value={symbol}>
          {symbol}
        </option>
      ))}
    </select>
  );
}
