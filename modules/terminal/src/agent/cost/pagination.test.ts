import { describe, expect, it } from "vitest";

import { pageOf } from "./pagination";

const rows = Array.from({ length: 23 }, (_, i) => i + 1);

describe("pageOf", () => {
  it("cuts the requested slice and counts it for a human", () => {
    const page = pageOf(rows, 1, 10);
    expect(page.rows).toEqual([11, 12, 13, 14, 15, 16, 17, 18, 19, 20]);
    expect(page.index).toBe(1);
    expect(page.count).toBe(3);
    expect(page.firstRow).toBe(11);
    expect(page.lastRow).toBe(20);
    expect(page.total).toBe(23);
  });

  it("gives a short last page rather than padding it", () => {
    const page = pageOf(rows, 2, 10);
    expect(page.rows).toEqual([21, 22, 23]);
    expect(page.lastRow).toBe(23);
  });

  it("clamps a page past the end instead of showing nothing", () => {
    // The case this module exists for: the operator is on page 4, narrows the date range,
    // and two rows come back. Storing the clamp would show one empty render first.
    const page = pageOf(rows.slice(0, 2), 3, 10);
    expect(page.index).toBe(0);
    expect(page.rows).toEqual([1, 2]);
    expect(page.count).toBe(1);
  });

  it("clamps a negative page the same way", () => {
    expect(pageOf(rows, -2, 10).index).toBe(0);
  });

  it("reports one empty page rather than none, so controls have something to say", () => {
    const page = pageOf([], 0, 10);
    expect(page.count).toBe(1);
    expect(page.rows).toEqual([]);
    expect(page.firstRow).toBe(0);
    expect(page.lastRow).toBe(0);
    expect(page.total).toBe(0);
  });

  it("does not paginate what fits", () => {
    const page = pageOf([1, 2, 3], 0, 10);
    expect(page.count).toBe(1);
    expect(page.rows).toEqual([1, 2, 3]);
  });
});
