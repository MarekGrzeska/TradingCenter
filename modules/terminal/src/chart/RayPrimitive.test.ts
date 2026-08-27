import { describe, expect, it, vi } from "vitest";
import type { CanvasRenderingTarget2D } from "fancy-canvas";
import type { IChartApi, ISeriesApi, SeriesAttachedParameter, SeriesType, Time } from "lightweight-charts";
import { RayPrimitive } from "./RayPrimitive";

/** A `CanvasRenderingContext2D` cannot be asserted on either, so this mocks the
 *  handful of drawing calls `RayPrimitive` actually makes and records them —
 *  the same "test what is asked for, not the pixels" boundary `testDoubles.ts`
 *  draws for the chart itself. */
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

function attach(ray: RayPrimitive, timeCoordinate: number | null, priceCoordinate: number | null) {
  const chart = {
    timeScale: () => ({
      timeToCoordinate: () => timeCoordinate,
      timeToIndex: () => null,
      logicalToCoordinate: () => null,
    }),
  } as unknown as IChartApi;
  const series = { priceToCoordinate: () => priceCoordinate } as unknown as ISeriesApi<SeriesType, Time>;
  ray.attached({ chart, series, requestUpdate: () => {} } as unknown as SeriesAttachedParameter<Time>);
}

describe("RayPrimitive", () => {
  it("has nothing to draw before it is attached", () => {
    const ray = new RayPrimitive("#fff");
    ray.setLevels([{ time: 100 as Time, price: 10, label: "PDH" }]);
    expect(ray.renderItems()).toEqual([]);
  });

  it("resolves x/y from the chart and series once attached", () => {
    const ray = new RayPrimitive("#fff");
    attach(ray, 120, 80);
    ray.setLevels([{ time: 100 as Time, price: 21000, label: "PDH" }]);

    expect(ray.renderItems()).toEqual([{ x: 120, y: 80, color: "#fff", label: "PDH" }]);
  });

  it("draws a segment from the level's own x to the right edge, not the whole width", () => {
    const ray = new RayPrimitive("#abc");
    attach(ray, 40, 90);
    ray.setLevels([{ time: 100 as Time, price: 21000, label: "PDH" }]);

    const { target, ctx } = fakeTarget(200);
    ray.paneViews()[0]?.renderer()?.draw(target);

    expect(ctx.moveTo).toHaveBeenCalledWith(40, 90.5);
    expect(ctx.lineTo).toHaveBeenCalledWith(200, 90.5);
    // On a plate rather than straight on the chart: the caption sits above the line, and the plate under
    // it is what keeps it readable over the wicks.
    expect(ctx.fillRect).toHaveBeenCalledWith(40, 73.5, 26, 14);
    expect(ctx.fillText).toHaveBeenCalledWith("PDH", 44, 80.5);
  });

  it("draws nothing for a level the time scale could not place", () => {
    const ray = new RayPrimitive("#abc");
    attach(ray, null, 90);
    ray.setLevels([{ time: 1 as Time, price: 21000, label: "PDH" }]);

    const { target, ctx } = fakeTarget(200);
    ray.paneViews()[0]?.renderer()?.draw(target);

    expect(ctx.moveTo).not.toHaveBeenCalled();
  });

  it("answers a click within tolerance of the line with the drawing's own id", () => {
    const drawn = new RayPrimitive("#abc", { weight: "drawing", objectId: "42" });
    attach(drawn, 40, 90);
    drawn.setLevels([{ time: 100 as Time, price: 21000, label: null }]);

    expect(drawn.hitTest(120, 90)).toEqual({
      externalId: "42",
      zOrder: "normal",
      cursorStyle: "pointer",
    });
    expect(drawn.hitTest(120, 93)?.externalId).toBe("42");
    expect(drawn.hitTest(120, 110)).toBeNull();
    expect(drawn.hitTest(10, 90)).toBeNull();
  });

  it("never answers a click for an indicator's own level", () => {
    // What a click picks out is an object somebody drew, not a reading.
    const computed = new RayPrimitive("#abc");
    attach(computed, 40, 90);
    computed.setLevels([{ time: 100 as Time, price: 21000, label: null }]);
    expect(computed.hitTest(120, 90)).toBeNull();
  });
});
