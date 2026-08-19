import { describe, expect, it, vi } from "vitest";
import type { CanvasRenderingTarget2D } from "fancy-canvas";
import type { IChartApi, ISeriesApi, SeriesAttachedParameter, SeriesType, Time } from "lightweight-charts";
import { TrendlinePrimitive } from "./TrendlinePrimitive";

function fakeContext() {
  return {
    save: vi.fn(),
    restore: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    stroke: vi.fn(),
    fillText: vi.fn(),
    fillRect: vi.fn(),
    // A width proportional to the text, so a chip's own geometry is predictable in a
    // test the way it is not in a real font metric.
    measureText: vi.fn((text: string) => ({ width: text.length * 6 })),
    setLineDash: vi.fn(),
    strokeStyle: "",
    lineWidth: 0,
    globalAlpha: 1,
    fillStyle: "",
    font: "",
    textBaseline: "",
  };
}

function fakeTarget(bitmapWidth: number) {
  const ctx = fakeContext();
  const target = {
    useBitmapCoordinateSpace: <T>(f: (scope: unknown) => T) =>
      f({
        context: ctx,
        mediaSize: { width: bitmapWidth, height: 300 },
        bitmapSize: { width: bitmapWidth, height: 300 },
        horizontalPixelRatio: 1,
        verticalPixelRatio: 1,
      }),
  } as unknown as CanvasRenderingTarget2D;
  return { ctx, target };
}

/** The time scale answers per moment here, not with one coordinate for everything: a
 *  trend line's two ends are the whole point, and a double that cannot tell them apart
 *  could not show a segment being drawn between them. Rising from (40, 200) to
 *  (260, 50) on screen unless a test overrides the x map. */
function attach(
  primitive: TrendlinePrimitive,
  xByTime: Map<number, number | null> = new Map([
    [100, 40],
    [200, 260],
  ]),
) {
  const yByPrice = new Map([
    [10, 200],
    [20, 50],
  ]);
  const chart = {
    timeScale: () => ({
      timeToCoordinate: (time: Time) => xByTime.get(time as number) ?? null,
      timeToIndex: () => null,
      logicalToCoordinate: () => null,
    }),
  } as unknown as IChartApi;
  const series = {
    priceToCoordinate: (price: number) => yByPrice.get(price) ?? null,
  } as unknown as ISeriesApi<SeriesType, Time>;
  primitive.attached({ chart, series, requestUpdate: () => {} } as unknown as SeriesAttachedParameter<Time>);
}

function aLine(overrides: Partial<Parameters<TrendlinePrimitive["setLines"]>[0][number]> = {}) {
  return {
    from: 100 as Time,
    to: 200 as Time,
    fromPrice: 10,
    toPrice: 20,
    label: null,
    color: null,
    ...overrides,
  };
}

describe("TrendlinePrimitive", () => {
  it("draws a segment between its two points and stops there", () => {
    const primitive = new TrendlinePrimitive("#fff");
    attach(primitive);
    primitive.setLines([aLine()]);

    const { ctx, target } = fakeTarget(400);
    primitive.paneViews()[0].renderer()?.draw(target);

    expect(ctx.moveTo).toHaveBeenCalledWith(40, 200);
    // Not the bitmap width: a ray runs to the right edge, a trend line does not.
    expect(ctx.lineTo).toHaveBeenCalledWith(260, 50);
  });

  it("draws nothing before it is attached to a chart", () => {
    const primitive = new TrendlinePrimitive("#fff");
    primitive.setLines([aLine()]);

    const { ctx, target } = fakeTarget(400);
    primitive.paneViews()[0].renderer()?.draw(target);

    expect(ctx.stroke).not.toHaveBeenCalled();
  });

  it("draws nothing when the time scale can place neither point", () => {
    const primitive = new TrendlinePrimitive("#fff");
    attach(primitive, new Map());
    primitive.setLines([aLine()]);

    const { ctx, target } = fakeTarget(400);
    primitive.paneViews()[0].renderer()?.draw(target);

    expect(ctx.stroke).not.toHaveBeenCalled();
  });

  it("is clicked on the segment, and near it, but not past its ends", () => {
    const drawn = new TrendlinePrimitive("#fff", { weight: "drawing", objectId: "8" });
    attach(drawn);
    drawn.setLines([aLine()]);

    // The midpoint of the segment, and three pixels off it.
    expect(drawn.hitTest(150, 125)?.externalId).toBe("8");
    expect(drawn.hitTest(150, 128)?.externalId).toBe("8");
    expect(drawn.hitTest(150, 160)).toBeNull();
    // On the line the segment lies on, but beyond where it was drawn to: a trend line
    // ends where the operator ended it (`terminal-chart` spec, "MUST NOT być przedłużana").
    expect(drawn.hitTest(400, -45)).toBeNull();
  });

  it("never answers a click for a primitive with no object behind it", () => {
    const primitive = new TrendlinePrimitive("#fff");
    attach(primitive);
    primitive.setLines([aLine()]);
    expect(primitive.hitTest(150, 125)).toBeNull();
  });
});
