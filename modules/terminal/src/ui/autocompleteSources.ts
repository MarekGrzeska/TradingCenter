import type { InstrumentSource } from "../data/source";
import type { AssetClass, Instrument } from "../data/types";
import type { OptionsFetcher, OptionsPage } from "./useAsyncOptions";

/** The `Autocomplete` sources the terminal actually uses, both of them in the
 *  instrument wizard. Each is just an `OptionsFetcher` closing over the source
 *  object it reads from — the component itself never knows which one it was
 *  given. (The grid's slot picker used to be a third; it is now a plain select
 *  over the archived pairs the grid already reads.) */

/**
 * Asset classes: a fixed, small set the gateway publishes, filtered locally
 * rather than round-tripped per keystroke — there is nothing a server-side
 * filter would do here that a substring match on a dozen strings does not
 * (terminal-instruments spec, "Klasy aktywów są wyliczalne").
 */
export function assetClassSource(instruments: InstrumentSource): OptionsFetcher<AssetClass> {
  return async (query, signal) => {
    const classes = await instruments.listAssetClasses(signal);
    const needle = query.trim().toUpperCase();
    const options = needle ? classes.filter((c) => c.includes(needle)) : classes;
    return { options };
  };
}

/**
 * Instruments within one class: an empty query enumerates the class (which
 * the gateway may cut short, `truncated` says so), a typed query searches
 * instead — the gateway's search is not bounded by the same node walk, so it
 * never truncates (terminal-instruments spec, "Wyliczenie instrumentów
 * klasy"; "Wyszukiwanie zawężone do klasy").
 */
export function instrumentInClassSource(
  instruments: InstrumentSource,
  assetClass: AssetClass,
): OptionsFetcher<Instrument> {
  return async (query, signal): Promise<OptionsPage<Instrument>> => {
    const trimmed = query.trim();
    if (!trimmed) {
      const page = await instruments.listInstruments(signal, assetClass);
      return { options: page.instruments, truncated: page.truncated };
    }
    const found = await instruments.searchInstruments(trimmed, signal, assetClass);
    return { options: found };
  };
}
