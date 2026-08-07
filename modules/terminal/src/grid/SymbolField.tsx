import { useEffect, useState } from "react";

/** Type a symbol straight into a slot without leaving the grid
 *  (terminal-grid spec, "Zmiana instrumentu w slocie"). The Instruments tab is
 *  the other way in, for when the symbol isn't already known. */
export function SymbolField({
  value,
  onCommit,
  label,
}: {
  value: string | null;
  onCommit(symbol: string): void;
  label: string;
}) {
  const [draft, setDraft] = useState(value ?? "");

  // Follow the slot when it changes from elsewhere (the Instruments tab
  // assigning into it, or a layout swap bringing a different slot forward).
  useEffect(() => {
    setDraft(value ?? "");
  }, [value]);

  function commit() {
    const symbol = draft.trim().toUpperCase();
    if (symbol && symbol !== value) {
      onCommit(symbol);
    } else if (!symbol) {
      setDraft(value ?? "");
    }
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        commit();
      }}
    >
      <input
        aria-label={label}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        placeholder="symbol"
        spellCheck={false}
        autoComplete="off"
        className="w-24 rounded border border-border bg-panel-strong px-1.5 py-0.5 text-xs font-semibold text-ink uppercase placeholder:font-normal placeholder:normal-case placeholder:text-ink-muted"
      />
    </form>
  );
}
