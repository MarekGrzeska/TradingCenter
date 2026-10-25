/**
 * The report's daily equity as the screen draws it, and the drawdown under it — measured the way the report measures its
 * own, from the starting capital, so the deepest point drawn is the drawdown the report states (`strategies-reports`).
 */

export interface Point {
  time: number;
  value: number;
}

export function equityPoints(equity: readonly (readonly [number, number | null])[]): Point[] {
  return equity.flatMap(([time, value]) => (value === null ? [] : [{ time, value }]));
}

export function drawdownPoints(points: readonly Point[], capital: number): Point[] {
  let peak = capital;
  return points.map(({ time, value }) => {
    peak = Math.max(peak, value);
    return { time, value: peak > 0 ? value / peak - 1 : 0 };
  });
}

/** A trade's moment as the start of the decision bar it fell in, which is where a chart can put a mark. */
export function barStart(epochSeconds: number, barSeconds: number): number {
  return epochSeconds - (epochSeconds % barSeconds);
}
