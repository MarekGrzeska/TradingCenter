import { describe, expect, it } from "vitest";
import { drawdownPoints, equityPoints } from "./curve";

describe("drawdownPoints", () => {
  it("measures from the starting capital, so its deepest point is the report's drawdown", () => {
    const points = equityPoints([
      [86400, 9_000],
      [172800, 11_000],
      [259200, null],
      [345600, 8_800],
    ]);

    const deepest = Math.min(...drawdownPoints(points, 10_000).map((p) => p.value));

    expect(points).toHaveLength(3);
    expect(deepest).toBeCloseTo(-0.2);
  });
});
