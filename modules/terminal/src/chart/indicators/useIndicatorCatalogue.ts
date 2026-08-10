import { useEffect, useState } from "react";
import type { IndicatorSource } from "../../data/source";
import type { IndicatorCatalogueEntry } from "../../data/types";

export type CatalogueStatus = "loading" | "ready" | "error";

export interface IndicatorCatalogueState {
  status: CatalogueStatus;
  entries: IndicatorCatalogueEntry[];
  error: string | null;
  retry(): void;
}

/**
 * The picker's whole vocabulary, read once and shared by every chart. A wskaźnik the
 * archive starts offering appears here without a terminal release — this hook is the
 * one place that turns the catalogue into something a picker can render
 * (`market-data-indicators` spec, "Katalog wystarcza do zbudowania wybieraka").
 */
export function useIndicatorCatalogue(
  source: IndicatorSource | undefined,
): IndicatorCatalogueState {
  const [status, setStatus] = useState<CatalogueStatus>("loading");
  const [entries, setEntries] = useState<IndicatorCatalogueEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!source) {
      setStatus("ready");
      setEntries([]);
      return;
    }
    let cancelled = false;
    const controller = new AbortController();
    setStatus("loading");
    setError(null);

    source
      .indicatorCatalogue(controller.signal)
      .then((catalogue) => {
        if (cancelled) return;
        setEntries(catalogue.indicators);
        setStatus("ready");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "could not read the indicator catalogue");
        setStatus("error");
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [source, attempt]);

  return { status, entries, error, retry: () => setAttempt((n) => n + 1) };
}
