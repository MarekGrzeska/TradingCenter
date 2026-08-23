import { useRead } from "../../data/query";
import type { IndicatorSource } from "../../data/source";
import type { IndicatorCatalogueEntry } from "../../data/types";

export type CatalogueStatus = "loading" | "ready" | "error";

export interface IndicatorCatalogueState {
  status: CatalogueStatus;
  entries: IndicatorCatalogueEntry[];
  error: string | null;
  retry(): void;
}

const NONE: IndicatorCatalogueEntry[] = [];

/**
 * The picker's whole vocabulary, read once and shared by every chart — one cache entry,
 * so six charts on a grid ask the archive once between them. An indicator the archive
 * starts offering appears here without a terminal release: this hook is the one place
 * that turns the catalogue into something a picker can render (`market-data-indicators`
 * spec, "Katalog wystarcza do zbudowania wybieraka").
 *
 * No source is not a failure — it is a chart with nothing to ask, and it renders an
 * empty picker rather than an error.
 */
export function useIndicatorCatalogue(
  source: IndicatorSource | undefined,
): IndicatorCatalogueState {
  const read = useRead({
    // **This key is owned here, and so is the shape behind it: the entries, not the
    // document.** The query cache is shared across the whole terminal and keyed by name
    // alone, so a second reader of this key holding the whole `IndicatorCatalogue` object
    // overwrites what the chart reads and `entries.map` stops being a function. That is not
    // hypothetical — the strategy configurator did it, and what broke was the chart grid.
    // Anything else that needs the catalogue calls this hook.
    key: ["archive", "indicator-catalogue"],
    read: async (signal) => (await source!.indicatorCatalogue(signal)).indicators,
    initial: NONE,
    fallbackMessage: "could not read the indicator catalogue",
    enabled: source !== undefined,
  });

  return {
    status: source === undefined ? "ready" : read.status,
    entries: read.value,
    error: read.error,
    retry: read.reload,
  };
}
