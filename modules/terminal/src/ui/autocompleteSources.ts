import type { InstrumentSource } from "../data/source";
import type { AssetClass, Instrument } from "../data/types";
import type { OptionsFetcher, OptionsPage } from "./useAsyncOptions";

/** The `Autocomplete` sources the terminal actually uses, both in the instrument wizard: each closes over the source
 *  object it reads from, so the component never knows which one it was given. */

/**
 * A fixed, small set the gateway publishes, filtered locally rather than round-tripped per keystroke: a server-side
 * filter does nothing here that a substring match on a dozen strings does not (terminal-instruments spec).
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
 * An empty query enumerates the class, which the gateway may cut short (`truncated` says so); a typed query searches
 * instead, and that path is not bounded by the same node walk, so it never truncates.
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
