import { resolveGatewayEndpoints } from "./config";
import { createGatewaySource } from "./gatewaySource";
import { createMockSource } from "./mockSource";
import type { MarketDataSource } from "./source";

export type SourceId = MarketDataSource["id"];

export interface SourceStore {
  subscribe(listener: () => void): () => void;
  getSnapshot(): MarketDataSource;
  getSourceId(): SourceId;
  setSource(id: SourceId): void;
}

/**
 * A `useSyncExternalStore`-compatible store holding the one active
 * `MarketDataSource` for the whole app — terminal-market-data spec,
 * "Przełączenie źródła": every view reads through this, none constructs a
 * source itself, so switching source needs no view to know it happened.
 * Sources are built lazily — picking "mock" as the default never touches the
 * gateway, and picking "gateway" never happens until an operator (or the env
 * default) asks for it.
 */
export function createSourceStore(
  defaultId: SourceId,
  buildSource: (id: SourceId) => MarketDataSource,
): SourceStore {
  let currentId = defaultId;
  let currentSource = buildSource(defaultId);
  const listeners = new Set<() => void>();

  return {
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    getSnapshot() {
      return currentSource;
    },
    getSourceId() {
      return currentId;
    },
    setSource(id) {
      if (id === currentId) return;
      currentId = id;
      currentSource = buildSource(id);
      for (const listener of listeners) listener();
    },
  };
}

function buildDefaultSource(id: SourceId): MarketDataSource {
  if (id === "mock") return createMockSource();
  const { httpBase, wsBase } = resolveGatewayEndpoints();
  return createGatewaySource(httpBase, wsBase);
}

export const sourceStore = createSourceStore(
  import.meta.env.VITE_DEFAULT_SOURCE === "gateway" ? "gateway" : "mock",
  buildDefaultSource,
);
