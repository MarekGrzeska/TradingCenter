import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { notifyManager } from "@tanstack/react-query";
import { queryClient } from "../data/query";

// Node takes Intl's default locale from the OS and, on Windows, from nothing else — LANG and LC_ALL are ignored — so
// `12431.toLocaleString()` differs between CI and a Polish machine. The views follow the operator's locale on purpose.
const formatNumber = Number.prototype.toLocaleString;
Number.prototype.toLocaleString = function (
  locales?: string | string[],
  options?: Intl.NumberFormatOptions,
): string {
  return formatNumber.call(this, locales ?? "en-US", options);
};

// jsdom implements neither of these, and the chart uses both: ResizeObserver
// for sizing, requestAnimationFrame to coalesce crosshair updates.
if (!("ResizeObserver" in globalThis)) {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// Node 22 and later ship a `localStorage` global that arrives in jsdom as a bare object with none of Storage's methods,
// so `.clear is not a function` reads like a bug in the code under test. Replaced rather than patched.
if (typeof globalThis.localStorage?.clear !== "function") {
  class MemoryStorage implements Storage {
    private entries = new Map<string, string>();

    get length(): number {
      return this.entries.size;
    }

    key(index: number): string | null {
      return [...this.entries.keys()][index] ?? null;
    }

    getItem(key: string): string | null {
      return this.entries.get(key) ?? null;
    }

    setItem(key: string, value: string): void {
      this.entries.set(key, String(value));
    }

    removeItem(key: string): void {
      this.entries.delete(key);
    }

    clear(): void {
      this.entries.clear();
    }
  }

  const storage = new MemoryStorage();
  for (const target of [globalThis, window]) {
    Object.defineProperty(target, "localStorage", {
      value: storage,
      configurable: true,
      writable: true,
    });
  }
}

// Every read goes through one cache (`data/query.ts`), so a test would answer from a fake archive since thrown away.
// Retries off too: a test asserting "unreachable" would otherwise wait out a real backoff.
queryClient.setDefaultOptions({ queries: { retry: false } });

// TanStack batches notifications behind its own scheduler, so a resolved re-read lands one macrotask after the timer
// that asked for it. Flushed here: the batching is a rendering optimisation, and every assertion is already in `act`.
notifyManager.setScheduler((flush) => flush());
afterEach(() => {
  queryClient.clear();
});
