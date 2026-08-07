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

