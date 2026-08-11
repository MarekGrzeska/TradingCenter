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
    setLineDash: vi.fn(),
    strokeStyle: "",
    lineWidth: 0,
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

/** `nearestBar` stands for what the real time scale answers when the moment asked for is
 *  not itself a bar: `null`/`null` is a chart with no bars to be near, a pair of numbers is
 *  the bar it would snap to. */
function attach(
  ray: RayPrimitive,
  timeCoordinate: number | null,
  priceCoordinate: number | null,
  nearestBar: { index: number | null; x: number | null } = { index: null, x: null },
) {
  const chart = {
    timeScale: () => ({
      timeToCoordinate: () => timeCoordinate,
      timeToIndex: () => nearestBar.index,
      logicalToCoordinate: () => nearestBar.x,
    }),
  } as unknown as IChartApi;
  const series = { priceToCoordinate: () => priceCoordinate } as unknown as ISeriesApi<SeriesType, Time>;
  const param = { chart, series, requestUpdate: () => {} } as unknown as SeriesAttachedParameter<Time>;
  ray.attached(param);
}

describe("RayPrimitive — a moment that is not a bar on this chart", () => {
  // A previous-day pivot's close moment is a midnight the venue may have been shut
  // through: inside the loaded range, and still not a bar of its own.
  it("snaps to the nearest bar instead of dropping the ray", () => {
    const ray = new RayPrimitive("#fff");
    attach(ray, null, 50, { index: 7, x: 240 });
    ray.setLevels([{ time: 100 as Time, price: 10, label: "PDH" }]);

    expect(ray.renderItems()[0]?.x).toBe(240);
  });

  it("still draws nothing when the chart holds no bars to be near", () => {
    const ray = new RayPrimitive("#fff");
    attach(ray, null, 50, { index: null, x: null });
    ray.setLevels([{ time: 100 as Time, price: 10, label: "PDH" }]);

    expect(ray.renderItems()[0]?.x).toBeNull();
  });
});

describe("RayPrimitive — coordinate resolution", () => {
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

  it("carries a null coordinate through rather than guessing one", () => {
    const ray = new RayPrimitive("#fff");
    attach(ray, null, 80);
    ray.setLevels([{ time: 100 as Time, price: 21000, label: "PDH" }]);

    expect(ray.renderItems()).toEqual([{ x: null, y: 80, color: "#fff", label: "PDH" }]);
  });

  it("stops resolving anything once detached", () => {
    const ray = new RayPrimitive("#fff");
    attach(ray, 120, 80);
    ray.detached();
    ray.setLevels([{ time: 100 as Time, price: 21000, label: "PDH" }]);

    expect(ray.renderItems()).toEqual([]);
  });
});

describe("RayPrimitive — drawing", () => {
  it("draws a segment from the level's own x to the right edge, not the whole width", () => {
    const ray = new RayPrimitive("#abc");
    attach(ray, 40, 90);
    ray.setLevels([{ time: 100 as Time, price: 21000, label: "PDH" }]);

    const { target, ctx } = fakeTarget(200);
    ray.paneViews()[0]?.renderer()?.draw(target);

    expect(ctx.moveTo).toHaveBeenCalledWith(40, 90.5);
    expect(ctx.lineTo).toHaveBeenCalledWith(200, 90.5);
    expect(ctx.stroke).toHaveBeenCalledTimes(1);
    expect(ctx.fillText).toHaveBeenCalledWith("PDH", 44, 86.5);
  });

  it("clamps a level whose moment sits left of the visible area to the pane's edge", () => {
    const ray = new RayPrimitive("#abc");
    attach(ray, -500, 90);
    ray.setLevels([{ time: 1 as Time, price: 21000, label: null }]);

    const { target, ctx } = fakeTarget(200);
    ray.paneViews()[0]?.renderer()?.draw(target);

    expect(ctx.moveTo).toHaveBeenCalledWith(0, 90.5);
  });

  it("draws nothing for a level the time scale could not place", () => {
    const ray = new RayPrimitive("#abc");
    attach(ray, null, 90);
    ray.setLevels([{ time: 1 as Time, price: 21000, label: "PDH" }]);

    const { target, ctx } = fakeTarget(200);
    ray.paneViews()[0]?.renderer()?.draw(target);

    expect(ctx.moveTo).not.toHaveBeenCalled();
  });
});
