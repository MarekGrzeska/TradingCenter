import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { useAsyncOptions } from "./useAsyncOptions";
import type { OptionsFetcher } from "./useAsyncOptions";

export interface AutocompleteProps<T> {
  value: T | null;
  onChange(value: T | null): void;
  /** Where positions come from — the only thing that differs between the
   *  terminal's three uses of this component (design.md, "Terminal: jeden
   *  `Autocomplete`, trzy źródła"). */
  source: OptionsFetcher<T>;
  getOptionId(option: T): string;
  getOptionLabel(option: T): string;
  renderOption?(option: T): React.ReactNode;
  placeholder?: string;
  ariaLabel: string;
  disabled?: boolean;
  /** Shown under the list when the source cut its answer short. */
  truncatedMessage?: string;
  /** Shown in place of the default "No matches." — a use site with its own
   *  reason for an empty list (e.g. nothing archived yet) says its own
   *  sentence instead of the generic one. */
  noResultsMessage?: string;
  /** How many came back, said out loud under a list that was *not* cut short
   *  — for a list an operator picks from to commit real collection work, the
   *  count is what tells them they are looking at all of it
   *  (terminal-instruments spec, "Katalog kompletny"). Omitted where a count
   *  would be noise, as with a handful of asset classes. */
  countLabel?(count: number): string;
}

/**
 * One reusable picker for the whole terminal — asset class, instrument in a class,
 * instrument already archived — behaving identically everywhere: arrows and Enter to
 * choose, Escape to close without disturbing the current choice, explicit empty and
 * failure states (terminal-instruments spec, "Podpowiadanie zachowuje się wszędzie tak
 * samo").
 *
 * A value and an open query are mutually exclusive: once something is chosen the field
 * shows it rather than an input, and clearing it is what returns to picking.
 */
export function Autocomplete<T>({
  value,
  onChange,
  source,
  getOptionId,
  getOptionLabel,
  renderOption,
  placeholder,
  ariaLabel,
  disabled = false,
  truncatedMessage = "List cut short — keep typing to narrow it down.",
  noResultsMessage = "No matches.",
  countLabel,
}: AutocompleteProps<T>) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const state = useAsyncOptions<T>(source, query, { enabled: open && !disabled });

  useEffect(() => {
    setHighlighted(0);
  }, [state.options]);

  function choose(option: T) {
    onChange(option);
    setOpen(false);
    setQuery("");
  }

  function clear() {
    onChange(null);
    setQuery("");
    setOpen(false);
    // The field just became an input again; keep the operator's hands where
    // they were rather than dropping focus.
    requestAnimationFrame(() => inputRef.current?.focus());
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      setHighlighted((i) => Math.min(i + 1, Math.max(state.options.length - 1, 0)));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlighted((i) => Math.max(i - 1, 0));
    } else if (event.key === "Enter") {
      const picked = state.options[highlighted];
      if (open && picked) {
        event.preventDefault();
        choose(picked);
      }
    } else if (event.key === "Escape") {
      if (open) {
        event.preventDefault();
        setOpen(false);
      }
    }
  }

  if (value !== null) {
    return (
      <div
        role="group"
        aria-label={ariaLabel}
        className="flex items-center gap-1.5 rounded border border-border bg-panel-strong px-2 py-1 text-sm text-ink"
      >
        <span className="min-w-0 flex-1 truncate">{getOptionLabel(value)}</span>
        <button
          type="button"
          aria-label={`Clear ${ariaLabel}`}
          onClick={clear}
          disabled={disabled}
          className="text-ink-muted hover:text-ink disabled:opacity-50"
        >
          ×
        </button>
      </div>
    );
  }

  return (
    <div className="relative">
      <input
        ref={inputRef}
        role="combobox"
        aria-label={ariaLabel}
        aria-expanded={open}
        aria-autocomplete="list"
        aria-controls={`${ariaLabel}-listbox`}
        value={query}
        disabled={disabled}
        placeholder={placeholder}
        onFocus={() => setOpen(true)}
        onChange={(event) => {
          setQuery(event.target.value);
          setOpen(true);
        }}
        onKeyDown={onKeyDown}
        onBlur={() => {
          // Deferred so a mousedown on an option (which fires before blur)
          // gets to select before the list disappears under it.
          setTimeout(() => setOpen(false), 100);
        }}
        autoComplete="off"
        spellCheck={false}
        className="w-full rounded border border-border bg-sunken px-2 py-1 text-sm text-ink placeholder:text-ink-faint disabled:opacity-50"
      />
      {open && (
        <ul
          id={`${ariaLabel}-listbox`}
          role="listbox"
          aria-label={ariaLabel}
          className="absolute z-10 mt-1 max-h-64 w-full min-w-max overflow-auto rounded border border-border-strong bg-raised text-sm shadow-lg"
        >
          {state.status === "loading" && (
            <li className="px-2 py-1.5 text-ink-muted">Loading…</li>
          )}
          {state.status === "error" && (
            <li className="flex items-center justify-between gap-2 px-2 py-1.5 text-critical">
              <span>{state.error}</span>
              <button
                type="button"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => state.retry()}
                className="shrink-0 rounded border border-border px-2 py-0.5 text-xs text-ink hover:bg-panel-strong"
              >
                Retry
              </button>
            </li>
          )}
          {state.status === "no-results" && (
            <li className="px-2 py-1.5 text-ink-muted">{noResultsMessage}</li>
          )}
          {state.status === "results" &&
            state.options.map((option, index) => (
              <li
                key={getOptionId(option)}
                role="option"
                aria-selected={index === highlighted}
                onMouseDown={(event) => {
                  // Fires before blur, so the click lands before the list
                  // unmounts under it.
                  event.preventDefault();
                  choose(option);
                }}
                onMouseEnter={() => setHighlighted(index)}
                className={`cursor-pointer px-2 py-1.5 ${
                  index === highlighted ? "bg-primary-soft text-ink" : "text-ink-secondary"
                }`}
              >
                {renderOption ? renderOption(option) : getOptionLabel(option)}
              </li>
            ))}
          {state.status === "results" &&
            (state.truncated ? (
              <li className="border-t border-border px-2 py-1.5 text-xs text-warning">
                {truncatedMessage}
              </li>
            ) : (
              // Only when nothing was cut short: a count under a truncated list
              // would read as the total when it is not one.
              countLabel && (
                <li className="border-t border-border px-2 py-1.5 text-xs text-ink-muted">
                  {countLabel(state.options.length)}
                </li>
              )
            ))}
        </ul>
      )}
    </div>
  );
}
