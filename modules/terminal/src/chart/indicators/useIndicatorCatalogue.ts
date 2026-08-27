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
 * The picker's whole vocabulary, read once and shared by every chart — six charts on a grid ask the archive
 * once between them. No source is not a failure: it is a chart with nothing to ask, and an empty picker.
 */
export function useIndicatorCatalogue(
  source: IndicatorSource | undefined,
): IndicatorCatalogueState {
  const read = useRead({
    // The shape behind this key is the entries, not the document: the cache is shared and keyed by name
    // alone, so the strategy configurator holding the whole object here broke `entries.map` in the grid.
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
