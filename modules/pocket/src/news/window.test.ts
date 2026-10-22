import { describe, expect, it } from "vitest";
import { limitFor, windowLabel } from "./window";

describe("windowLabel", () => {
  it.each([
    [5, "last 5 min"],
    [15, "last 15 min"],
    [60, "last 1 h"],
    [240, "last 4 h"],
    [1440, "last 1 d"],
    [10080, "last 7 d"],
  ])("names %i minutes", (minutes, label) => {
    expect(windowLabel(minutes)).toBe(label);
  });
});

describe("limitFor", () => {
  it("asks for the most only when the window is a day or more", () => {
    expect(limitFor(240)).toBe(300);
    expect(limitFor(1440)).toBe(1000);
    expect(limitFor(10080)).toBe(1000);
  });
});
