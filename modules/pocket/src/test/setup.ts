import "@testing-library/jest-dom/vitest";

// Node 22 and later ship a `localStorage` global that arrives in jsdom as a bare object with none of
// Storage's methods, so `.clear is not a function` reads like a bug in the code under test.
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
