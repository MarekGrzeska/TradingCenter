import { archive } from "../data/marketData";
import { Autocomplete } from "../ui/Autocomplete";
import { archivedInstrumentSource } from "../ui/autocompleteSources";
import type { ArchivedInstrument } from "../ui/autocompleteSources";

/**
 * The only way a symbol reaches a slot: picked from what the archive is
 * actually collecting, never typed from memory — a chart for a pair nobody
 * archives has nothing to show, and the old text field only said so after
 * the fact (terminal-grid spec, "Slot przyjmuje wyłącznie instrument
 * archiwizowany"). Suggestions that come up empty, or a list that could not
 * be read, point at the Instruments tab — that is where an instrument gets
 * added to the archive in the first place.
 */
export function SymbolField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: ArchivedInstrument | null;
  onChange(instrument: ArchivedInstrument | null): void;
}) {
  return (
    <Autocomplete<ArchivedInstrument>
      value={value}
      onChange={onChange}
      source={archivedInstrumentSource(archive)}
      getOptionId={(instrument) => instrument.symbol}
      getOptionLabel={(instrument) => instrument.symbol}
      renderOption={(instrument) => (
        <span className="flex items-center gap-2">
          <span className="font-semibold text-ink">{instrument.symbol}</span>
          <span className="text-ink-muted">{instrument.resolutions.join(" · ")}</span>
        </span>
      )}
      ariaLabel={label}
      placeholder="Symbol…"
      noResultsMessage="Nothing archived matches — add instruments in the Instruments tab."
    />
  );
}
