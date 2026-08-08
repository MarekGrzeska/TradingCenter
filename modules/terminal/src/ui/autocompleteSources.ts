import type { ArchiveAdmin, InstrumentSource } from "../data/source";
import type { AssetClass, Instrument, Resolution } from "../data/types";
import type { OptionsFetcher, OptionsPage } from "./useAsyncOptions";

/** The three `Autocomplete` sources the terminal actually uses (design.md,
 *  "Terminal: jeden `Autocomplete`, trzy źródła"). Each is just an
 *  `OptionsFetcher` closing over the source object it reads from — the
 *  component itself never knows which one it was given. */

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

/** One symbol as the archive is collecting it, in every resolution being
 *  collected — the grouping `/pairs` does not do itself (design.md,
 *  "Grupowanie `/pairs` po symbolu robi terminal"). */
export interface ArchivedInstrument {
  symbol: string;
  resolutions: Resolution[];
}

/**
 * Instruments already archived, grouped from `/pairs` by symbol and filtered
 * locally by symbol — the archive has no search of its own and does not need
 * one at the sizes `MAX_TRACKED_PAIRS` allows (terminal-grid spec, "Slot
 * przyjmuje wyłącznie instrument archiwizowany").
 */
export function archivedInstrumentSource(archive: ArchiveAdmin): OptionsFetcher<ArchivedInstrument> {
  return async (query, signal) => {
    const pairs = await archive.listPairs(signal);
    const bySymbol = new Map<string, Resolution[]>();
    for (const pair of pairs) {
      const resolutions = bySymbol.get(pair.symbol) ?? [];
      resolutions.push(pair.resolution);
      bySymbol.set(pair.symbol, resolutions);
    }
    const needle = query.trim().toUpperCase();
    const options: ArchivedInstrument[] = [...bySymbol.entries()]
      .filter(([symbol]) => !needle || symbol.includes(needle))
      .map(([symbol, resolutions]) => ({ symbol, resolutions }))
      .sort((a, b) => a.symbol.localeCompare(b.symbol));
    return { options };
  };
}
