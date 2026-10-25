import { describe, expect, it } from "vitest";
import { barsIn, runsGoing } from "./present";

describe("runsGoing", () => {
  it.each([
    [1, "Zniknie 1 uruchomienie"],
    [3, "Znikną 3 uruchomienia"],
    [5, "Zniknie 5 uruchomień"],
    [12, "Zniknie 12 uruchomień"],
    [22, "Znikną 22 uruchomienia"],
  ])("counts %i the Polish way", (count, said) => {
    expect(runsGoing(count)).toBe(said);
  });
});

describe("barsIn", () => {
  it("counts candles of the resolution, calendar time", () => {
    const from = new Date("2026-01-01T00:00:00Z");
    const to = new Date("2026-01-02T00:00:00Z");

    expect(barsIn(from, to, "MINUTE")).toBe(1440);
    expect(barsIn(from, to, "MINUTE_5")).toBe(288);
  });
});
