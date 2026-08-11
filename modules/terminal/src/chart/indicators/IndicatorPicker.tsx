import { useState } from "react";
import type { IndicatorCatalogueEntry, IndicatorSelection } from "../../data/types";

export interface IndicatorPickerProps {
  entries: IndicatorCatalogueEntry[];
  selections: IndicatorSelection[];
  onChange(selections: IndicatorSelection[]): void;
  /** Whether this chart draws the entry's render style yet. Kept out of the picker's
   *  own logic on purpose — the picker knows nothing about panes or draw styles, only
   *  that some caller-supplied predicate decides what may be picked. */
  canDraw(entry: IndicatorCatalogueEntry): boolean;
}

function defaultParams(entry: IndicatorCatalogueEntry): Record<string, number> {
  return Object.fromEntries(entry.params.map((p) => [p.name, p.default]));
}

/**
 * Built entirely from the catalogue it is given — no indicator is named in this file.
 * Adding one to `market_data/indicators/catalogue/` makes it appear here without a
 * change on this side, as long as its output shape and render style are ones `canDraw`
 * already accepts (`market-data-indicators` spec, "Katalog wystarcza do zbudowania
 * wybieraka"; `terminal-chart` spec, "Operator wybiera wskaźniki z tego, co oferuje
 * źródło").
 */
export function IndicatorPicker({ entries, selections, onChange, canDraw }: IndicatorPickerProps) {
  const [open, setOpen] = useState(false);
  const [paramErrors, setParamErrors] = useState<Record<string, string>>({});

  function toggle(entry: IndicatorCatalogueEntry) {
    const active = selections.some((s) => s.id === entry.id);
    onChange(
      active
        ? selections.filter((s) => s.id !== entry.id)
        : [...selections, { id: entry.id, params: defaultParams(entry) }],
    );
  }

  function setParam(entry: IndicatorCatalogueEntry, paramName: string, raw: string) {
    const key = `${entry.id}.${paramName}`;
    const spec = entry.params.find((p) => p.name === paramName);
    if (!spec) return;
    const value = Number(raw);
    if (!Number.isFinite(value) || value < spec.min || value > spec.max) {
      setParamErrors((prev) => ({
        ...prev,
        [key]: `${spec.name} must be between ${spec.min} and ${spec.max}`,
      }));
      return;
    }
    setParamErrors((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
    onChange(
      selections.map((s) =>
        s.id === entry.id ? { ...s, params: { ...s.params, [paramName]: value } } : s,
      ),
    );
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-label="Indicators"
        className="rounded border border-border px-1.5 py-0.5 text-xs text-ink hover:bg-panel-strong"
      >
        Indicators{selections.length > 0 ? ` (${selections.length})` : ""}
      </button>

      {open && (
        <div
          role="listbox"
          aria-label="Available indicators"
          className="absolute right-0 top-full z-20 mt-1 max-h-80 w-64 overflow-y-auto rounded border border-border bg-panel p-2 shadow-lg"
        >
          {entries.length === 0 && (
            <p className="p-1 text-xs text-ink-muted">No indicators available.</p>
          )}
          {entries.map((entry) => {
            const selection = selections.find((s) => s.id === entry.id);
            const drawable = canDraw(entry);
            return (
              <div key={entry.id} className="border-b border-border py-1.5 last:border-b-0">
                <label
                  className={`flex items-center gap-2 text-xs ${drawable ? "text-ink" : "text-ink-muted"}`}
                  title={
                    drawable
                      ? undefined
                      : "This chart cannot draw this indicator's render style yet."
                  }
                >
                  <input
                    type="checkbox"
                    checked={Boolean(selection)}
                    disabled={!drawable}
                    onChange={() => toggle(entry)}
                  />
                  <span title={entry.name}>{entry.id.toUpperCase()}</span>
                </label>

                {selection && entry.params.length > 0 && (
                  <div className="ml-5 mt-1 flex flex-wrap gap-2">
                    {entry.params.map((param) => {
                      const errorKey = `${entry.id}.${param.name}`;
                      return (
                        <div key={param.name} className="flex flex-col">
                          <label
                            className="text-[10px] text-ink-muted"
                            htmlFor={`indicator-param-${entry.id}-${param.name}`}
                          >
                            {param.name}
                          </label>
                          <input
                            id={`indicator-param-${entry.id}-${param.name}`}
                            type="number"
                            defaultValue={selection.params[param.name]}
                            min={param.min}
                            max={param.max}
                            step={param.type === "int" ? 1 : "any"}
                            className="w-16 rounded border border-border bg-panel-strong px-1 py-0.5 text-xs text-ink"
                            onBlur={(e) => setParam(entry, param.name, e.target.value)}
                          />
                          {paramErrors[errorKey] && (
                            <span className="text-[10px] text-critical">{paramErrors[errorKey]}</span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
