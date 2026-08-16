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
 *  could not show a segment being drawn between them. */
function attach(
  primitive: TrendlinePrimitive,
  xByTime: Map<number, number | null>,
  yByPrice: Map<number, number | null>,
  nearestBar: { index: number | null; x: number | null } = { index: null, x: null },
) {
  const chart = {
    timeScale: () => ({
      timeToCoordinate: (time: Time) => xByTime.get(time as number) ?? null,
      timeToIndex: () => nearestBar.index,
      logicalToCoordinate: () => nearestBar.x,
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
    attach(
      primitive,
      new Map([
        [100, 40],
        [200, 260],
      ]),
      new Map([
        [10, 200],
        [20, 50],
      ]),
    );
    primitive.setLines([aLine()]);

    const { ctx, target } = fakeTarget(400);
    primitive.paneViews()[0].renderer()?.draw(target);

    expect(ctx.moveTo).toHaveBeenCalledWith(40, 200);
    // Not the bitmap width: a ray runs to the right edge, a trend line does not.
    expect(ctx.lineTo).toHaveBeenCalledWith(260, 50);
  });

  it("keeps its slope when one point is off the left edge", () => {
    // Clamping the near end to zero the way `RayPrimitive` does would tilt the line —
    // the coordinate is negative and stays negative, and the canvas clips it.
    const primitive = new TrendlinePrimitive("#fff");
    attach(
      primitive,
      new Map([
        [100, -120],
        [200, 260],
      ]),
      new Map([
        [10, 200],
        [20, 50],
      ]),
    );
    primitive.setLines([aLine()]);

    const { ctx, target } = fakeTarget(400);
    primitive.paneViews()[0].renderer()?.draw(target);

    expect(ctx.moveTo).toHaveBeenCalledWith(-120, 200);
  });

  it("draws a line whose both ends are outside the visible range", () => {
    // Neither end is on screen and the segment still crosses it — the case a
    // visible-range filter would wrongly skip.
    const primitive = new TrendlinePrimitive("#fff");
    attach(
      primitive,
      new Map([
        [100, -300],
        [200, 900],
      ]),
      new Map([
        [10, 200],
        [20, 50],
      ]),
    );
    primitive.setLines([aLine()]);

    const { ctx, target } = fakeTarget(400);
    primitive.paneViews()[0].renderer()?.draw(target);

    expect(ctx.stroke).toHaveBeenCalledTimes(1);
  });

  it("snaps a moment that is not a bar to the nearest one", () => {
    const primitive = new TrendlinePrimitive("#fff");
    attach(
      primitive,
      new Map([[200, 260]]), // 100 has no bar of its own
      new Map([
        [10, 200],
        [20, 50],
      ]),
      { index: 3, x: 40 },
    );
    primitive.setLines([aLine()]);

    const { ctx, target } = fakeTarget(400);
    primitive.paneViews()[0].renderer()?.draw(target);

    expect(ctx.moveTo).toHaveBeenCalledWith(40, 200);
  });

  it("draws nothing when the time scale can place neither point", () => {
    const primitive = new TrendlinePrimitive("#fff");
    attach(primitive, new Map(), new Map([[10, 200], [20, 50]]));
    primitive.setLines([aLine()]);

    const { ctx, target } = fakeTarget(400);
    primitive.paneViews()[0].renderer()?.draw(target);

    expect(ctx.stroke).not.toHaveBeenCalled();
  });

  it("draws nothing when a price falls outside the price scale", () => {
    const primitive = new TrendlinePrimitive("#fff");
    attach(
      primitive,
      new Map([
        [100, 40],
        [200, 260],
      ]),
      new Map([[10, 200]]), // 20 has no coordinate
    );
    primitive.setLines([aLine()]);

    const { ctx, target } = fakeTarget(400);
    primitive.paneViews()[0].renderer()?.draw(target);

    expect(ctx.stroke).not.toHaveBeenCalled();
  });

  it("draws nothing before it is attached to a chart", () => {
    const primitive = new TrendlinePrimitive("#fff");
    primitive.setLines([aLine()]);

    const { ctx, target } = fakeTarget(400);
    primitive.paneViews()[0].renderer()?.draw(target);

    expect(ctx.stroke).not.toHaveBeenCalled();
  });

  it("uses the line's own colour when it has one, and the chart's when it does not", () => {
    const primitive = new TrendlinePrimitive("#chart");
    attach(
      primitive,
      new Map([
        [100, 40],
        [200, 260],
      ]),
      new Map([
        [10, 200],
        [20, 50],
      ]),
    );

    primitive.setLines([aLine({ color: "#own" })]);
    const own = fakeTarget(400);
    primitive.paneViews()[0].renderer()?.draw(own.target);
    expect(own.ctx.strokeStyle).toBe("#own");

    primitive.setLines([aLine({ color: null })]);
    const fallback = fakeTarget(400);
    primitive.paneViews()[0].renderer()?.draw(fallback.target);
    expect(fallback.ctx.strokeStyle).toBe("#chart");
  });

  it("puts the label at the later end", () => {
    const primitive = new TrendlinePrimitive("#fff");
    attach(
      primitive,
      new Map([
        [100, 40],
        [200, 260],
      ]),
      new Map([
        [10, 200],
        [20, 50],
      ]),
    );
    primitive.setLines([aLine({ label: "trend" })]);

    const { ctx, target } = fakeTarget(400);
    primitive.paneViews()[0].renderer()?.draw(target);

    expect(ctx.fillText).toHaveBeenCalledWith("trend", 264, 40);
  });
});

describe("TrendlinePrimitive — an operator's own line (terminal-chart-objects spec)", () => {
  /** Rising from (40, 200) to (260, 50) on screen — the two ends the tests measure a
   *  click against. */
  function drawnLine() {
    const primitive = new TrendlinePrimitive("#fff", {
      weight: "drawing",
      objectId: "8",
      palette: { onFill: "#000", support: "#up", resistance: "#down" },
    });
    attach(
      primitive,
      new Map([
        [100, 40],
        [200, 260],
      ]),
      new Map([
        [10, 200],
        [20, 50],
      ]),
    );
    primitive.setLines([aLine()]);
    return primitive;
  }

  it("draws an operator's line heavier and unbroken", () => {
    const drawn = drawnLine();
    const { target, ctx } = fakeTarget(400);
    drawn.paneViews()[0].renderer()?.draw(target);
    expect(ctx.lineWidth).toBe(2);
    expect(ctx.setLineDash).toHaveBeenCalledWith([]);
  });

  it("says both of its ends at the axis", () => {
    const drawn = drawnLine();
    drawn.setCurrentPrice(15);
    const views = drawn.priceAxisViews();
    expect(views).toHaveLength(2);
    expect(views[0].backColor()).toBe("#up");
    expect(views[1].backColor()).toBe("#down");
  });

  it("is clicked on the segment, and near it, but not past its ends", () => {
    const drawn = drawnLine();
    // The midpoint of the segment, and three pixels off it.
    expect(drawn.hitTest(150, 125)?.externalId).toBe("8");
    expect(drawn.hitTest(150, 128)?.externalId).toBe("8");
    expect(drawn.hitTest(150, 160)).toBeNull();
    // On the line the segment lies on, but beyond where it was drawn to: a trend line
    // ends where the operator ended it (`terminal-chart` spec, "MUST NOT być przedłużana").
    expect(drawn.hitTest(400, -45)).toBeNull();
  });

  it("never answers for a primitive with no object behind it", () => {
    const primitive = new TrendlinePrimitive("#fff");
    attach(
      primitive,
      new Map([
        [100, 40],
        [200, 260],
      ]),
      new Map([
        [10, 200],
        [20, 50],
      ]),
    );
    primitive.setLines([aLine()]);
    expect(primitive.hitTest(150, 125)).toBeNull();
  });
});
