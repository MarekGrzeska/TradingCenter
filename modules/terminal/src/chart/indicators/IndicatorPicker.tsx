import { useState } from "react";
import {
  newIndicatorSelectionKey,
  type IndicatorCatalogueEntry,
  type IndicatorSelection,
} from "../../data/types";
import { INDICATOR_LINE_TOKENS } from "../theme";
import { Button } from "../../ui/Button";

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

function newInstance(entry: IndicatorCatalogueEntry): IndicatorSelection {
  return {
    key: newIndicatorSelectionKey(),
    id: entry.id,
    params: defaultParams(entry),
    color: null,
  };
}

/** Everything an operator might reasonably type to mean this entry. `group` is in here
 *  deliberately: with sixty-odd entries, "zones" or "oscillators" is the search most
 *  worth answering, and the catalogue already carries the grouping the server chose. */
function haystack(entry: IndicatorCatalogueEntry): string[] {
  return [entry.id, entry.name, entry.group, ...entry.aliases];
}

function matches(entry: IndicatorCatalogueEntry, needle: string): boolean {
  return haystack(entry).some((text) => text.toLowerCase().includes(needle));
}

/**
 * The alias a search hit, when the visible label does not already explain the hit — typing "fair value
 * gap" must not return a row that only says `RANGE_GAP`. Null when the id or the name carries the match.
 */
function matchedAlias(entry: IndicatorCatalogueEntry, needle: string): string | null {
  if (!needle) return null;
  if (entry.id.toLowerCase().includes(needle) || entry.name.toLowerCase().includes(needle)) {
    return null;
  }
  return entry.aliases.find((alias) => alias.toLowerCase().includes(needle)) ?? null;
}

/**
 * Built entirely from the catalogue it is given, so a new archive entry appears here untouched. An entry may
 * be chosen more than once: the checkbox is its on/off, each instance below carries its own params and colour.
 */
export function IndicatorPicker({ entries, selections, onChange, canDraw }: IndicatorPickerProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [paramErrors, setParamErrors] = useState<Record<string, string>>({});

  const needle = query.trim().toLowerCase();
  // Filtering hides, it does not deselect: `selections` is the state and this list is only a view of the
  // catalogue. A selected entry filtered out of view stays computed and drawn.
  const shown = needle ? entries.filter((entry) => matches(entry, needle)) : entries;

  function close() {
    setOpen(false);
    // Reopening starts from the whole catalogue. A filter left over from the last time
    // reads as a catalogue that lost entries, which is a real state this picker also has.
    setQuery("");
  }

  function instancesOf(entry: IndicatorCatalogueEntry): IndicatorSelection[] {
    return selections.filter((s) => s.id === entry.id);
  }

  function toggle(entry: IndicatorCatalogueEntry) {
    const active = selections.some((s) => s.id === entry.id);
    onChange(
      active ? selections.filter((s) => s.id !== entry.id) : [...selections, newInstance(entry)],
    );
  }

  function addInstance(entry: IndicatorCatalogueEntry) {
    onChange([...selections, newInstance(entry)]);
  }

  function removeInstance(key: string) {
    onChange(selections.filter((s) => s.key !== key));
    setParamErrors((prev) =>
      Object.fromEntries(Object.entries(prev).filter(([k]) => !k.startsWith(`${key}.`))),
    );
  }

  function setColor(key: string, color: string | null) {
    onChange(selections.map((s) => (s.key === key ? { ...s, color } : s)));
  }

  function setParam(
    entry: IndicatorCatalogueEntry,
    selection: IndicatorSelection,
    paramName: string,
    raw: string,
  ) {
    const errorKey = `${selection.key}.${paramName}`;
    const spec = entry.params.find((p) => p.name === paramName);
    if (!spec) return;
    const value = Number(raw);
    if (!Number.isFinite(value) || value < spec.min || value > spec.max) {
      setParamErrors((prev) => ({
        ...prev,
        [errorKey]: `${spec.name} must be between ${spec.min} and ${spec.max}`,
      }));
      return;
    }
    setParamErrors((prev) => {
      const next = { ...prev };
      delete next[errorKey];
      return next;
    });
    onChange(
      selections.map((s) =>
        s.key === selection.key ? { ...s, params: { ...s.params, [paramName]: value } } : s,
      ),
    );
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => (open ? close() : setOpen(true))}
        aria-expanded={open}
        aria-label="Indicators"
        // `h-6`, matching the resolution select beside it: a native `<select>`'s own sizing runs taller
        // than a `<button>`'s given the same padding.
        className="h-6 rounded border border-border px-1.5 text-xs text-ink hover:bg-panel-strong"
      >
        Indicators{selections.length > 0 ? ` (${selections.length})` : ""}
      </button>

      {open && (
        // Left-anchored: the button sits near the left edge of the header. A right-anchored panel would
        // pin its right edge to the button's and grow leftward, running off the header entirely.
        <div className="absolute left-0 top-full z-20 mt-1 flex max-h-80 w-72 flex-col rounded border border-border-strong bg-raised shadow-lg">
          {/* Outside the listbox, not inside it: a text field is not one of the options,
              and the catalogue is long enough that this is the first thing an operator
              reaches for. */}
          <input
            type="search"
            value={query}
            autoFocus
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") close();
            }}
            placeholder="Filter…"
            aria-label="Filter indicators"
            className="m-2 mb-0 shrink-0 rounded border border-border bg-sunken px-1.5 py-1 text-xs text-ink placeholder:text-ink-faint"
          />

          <div
            role="listbox"
            aria-label="Available indicators"
            className="min-h-0 overflow-y-auto p-2"
          >
          {entries.length === 0 && (
            <p className="p-1 text-xs text-ink-muted">No indicators available.</p>
          )}
          {entries.length > 0 && shown.length === 0 && (
            // Deliberately not the message above. "Nothing offered" and "nothing matched
            // what you typed" are different states, and one of them you fix by typing less.
            <p className="p-1 text-xs text-ink-muted">No indicator matches “{query.trim()}”.</p>
          )}
          {shown.map((entry) => {
            const instances = instancesOf(entry);
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
                    checked={instances.length > 0}
                    disabled={!drawable}
                    onChange={() => toggle(entry)}
                  />
                  <span title={entry.name}>{entry.id.toUpperCase()}</span>
                </label>

                {/* Outside the label on purpose: inside it, this text joins the
                    checkbox's accessible name, and "EMA" stops being how you find it. */}
                <span className="ml-5 block text-[10px] text-ink-muted">
                  {matchedAlias(entry, needle) ?? entry.name}
                </span>

                {instances.map((selection, index) => (
                  <IndicatorInstance
                    key={selection.key}
                    entry={entry}
                    selection={selection}
                    // 1-based and by position among this entry's instances: the operator
                    // is looking at a list, not at keys.
                    ordinal={index + 1}
                    // A lone instance needs no ordinal to be identified by, and naming it
                    // "EMA 1" would suggest a second one exists.
                    named={instances.length > 1}
                    paramErrors={paramErrors}
                    onParam={(paramName, raw) => setParam(entry, selection, paramName, raw)}
                    onColor={(color) => setColor(selection.key, color)}
                    onRemove={() => removeInstance(selection.key)}
                  />
                ))}

                {instances.length > 0 && (
                  <Button
                    tone="muted"
                    size="2xs"
                    className="ml-5 mt-1"
                    onClick={() => addInstance(entry)}
                  >
                    + Add another {entry.id.toUpperCase()}
                  </Button>
                )}
              </div>
            );
          })}
          </div>
        </div>
      )}
    </div>
  );
}

interface IndicatorInstanceProps {
  entry: IndicatorCatalogueEntry;
  selection: IndicatorSelection;
  ordinal: number;
  named: boolean;
  paramErrors: Record<string, string>;
  onParam(paramName: string, raw: string): void;
  onColor(color: string | null): void;
  onRemove(): void;
}

/** One chosen instance: its params, its colour, and its own way out. Grouped and named,
 *  because with three EMAs open the controls are otherwise three identical rows. */
function IndicatorInstance({
  entry,
  selection,
  ordinal,
  named,
  paramErrors,
  onParam,
  onColor,
  onRemove,
}: IndicatorInstanceProps) {
  const label = named ? `${entry.id.toUpperCase()} ${ordinal}` : entry.id.toUpperCase();

  return (
    <div role="group" aria-label={label} className="ml-5 mt-1 border-l border-border pl-2">
      <div className="flex flex-wrap items-end gap-2">
        {entry.params.map((param) => {
          const errorKey = `${selection.key}.${param.name}`;
          return (
            <div key={param.name} className="flex flex-col">
              <label
                className="text-[10px] text-ink-muted"
                htmlFor={`indicator-param-${selection.key}-${param.name}`}
              >
                {param.name}
              </label>
              <input
                id={`indicator-param-${selection.key}-${param.name}`}
                type="number"
                defaultValue={selection.params[param.name]}
                min={param.min}
                max={param.max}
                step={param.type === "int" ? 1 : "any"}
                className="w-16 rounded border border-border bg-sunken px-1 py-0.5 text-xs text-ink"
                onBlur={(e) => onParam(param.name, e.target.value)}
              />
              {paramErrors[errorKey] && (
                <span className="text-[10px] text-critical">{paramErrors[errorKey]}</span>
              )}
            </div>
          );
        })}

        <Button
          tone="muted"
          size="2xs"
          onClick={onRemove}
          aria-label={`Remove ${label}`}
        >
          Remove
        </Button>
      </div>

      <div className="mt-1 flex flex-wrap items-center gap-1">
        {INDICATOR_LINE_TOKENS.map((token, index) => (
          <button
            key={token}
            type="button"
            onClick={() => onColor(token)}
            aria-label={`Colour ${index + 1}`}
            aria-pressed={selection.color === token}
            // The token is the CSS variable itself, so the swatch and the line it stands
            // for read the same value — one definition, both consumers (`theme.ts`).
            style={{ backgroundColor: `var(${token})` }}
            className={`h-3.5 w-3.5 rounded-sm border ${
              selection.color === token ? "border-ink" : "border-border"
            }`}
          />
        ))}
        <button
          type="button"
          onClick={() => onColor(null)}
          aria-pressed={selection.color === null}
          className={`rounded border px-1 text-[10px] ${
            selection.color === null ? "border-ink text-ink" : "border-border text-ink-muted"
          }`}
        >
          Auto
        </button>
      </div>
    </div>
  );
}
