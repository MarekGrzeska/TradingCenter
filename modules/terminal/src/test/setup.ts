import "@testing-library/jest-dom/vitest";

// jsdom implements neither of these, and the chart uses both: ResizeObserver
// for sizing, requestAnimationFrame to coalesce crosshair updates.
if (!("ResizeObserver" in globalThis)) {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// Node 20 had no `localStorage`; Node 22 and later ship one as a global, and it
// arrives in the jsdom environment as a bare object with none of Storage's
// methods on it — `window.localStorage === globalThis.localStorage`, and
// `.clear` is undefined. Anything reading a stored grid layout then fails with
// "localStorage.clear is not a function", which reads like a bug in the code
// under test rather than a collision between two runtimes' globals.
//
// Replaced rather than patched: a half-working Storage is worse than an
// obviously fake one, and the tests want a clean slate per file anyway.
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
