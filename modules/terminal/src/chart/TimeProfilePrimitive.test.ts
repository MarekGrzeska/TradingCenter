import { describe, expect, it, vi } from "vitest";
import type { CanvasRenderingTarget2D } from "fancy-canvas";
import type { ISeriesApi, SeriesAttachedParameter, SeriesType, Time } from "lightweight-charts";
import { TimeProfilePrimitive, type ProfileColors } from "./TimeProfilePrimitive";

const COLORS: ProfileColors = { bar: "#888", pointOfControl: "#0af" };

function fakeContext() {
  return { fillRect: vi.fn(), fillStyle: "" };
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

function attach(primitive: TimeProfilePrimitive, priceToCoordinate: (price: number) => number | null) {
  const series = { priceToCoordinate } as unknown as ISeriesApi<SeriesType, Time>;
  const param = {
    chart: {},
    series,
    requestUpdate: () => {},
  } as unknown as SeriesAttachedParameter<Time>;
  primitive.attached(param);
}

describe("TimeProfilePrimitive", () => {
  it("has nothing to draw before it is attached", () => {
    const primitive = new TimeProfilePrimitive(COLORS);
    primitive.setBars([{ price: 100, count: 5, isPointOfControl: true }]);
    expect(primitive.renderItems()).toEqual([]);
  });

  it("sizes every bar's share against the busiest bucket in the same read", () => {
    const primitive = new TimeProfilePrimitive(COLORS);
    attach(primitive, (p) => p);
    primitive.setBars([
      { price: 100, count: 5, isPointOfControl: false },
      { price: 101, count: 20, isPointOfControl: true },
      { price: 102, count: 10, isPointOfControl: false },
    ]);

    const items = primitive.renderItems();
    expect(items.map((i) => i.share)).toEqual([0.25, 1, 0.5]);
    // The point of control is coloured apart from every other bucket.
    expect(items.map((i) => i.color)).toEqual([COLORS.bar, COLORS.pointOfControl, COLORS.bar]);
  });

  it("fills a bar reaching from the pane's right edge, sized by its own share", () => {
    const primitive = new TimeProfilePrimitive(COLORS);
    attach(primitive, () => 90);
    primitive.setBars([{ price: 100, count: 10, isPointOfControl: true }]);

    const { target, ctx } = fakeTarget(1000);
    primitive.paneViews()[0]?.renderer()?.draw(target);

    // share=1 (only bar) × 22% of 1000px width = 220px, reaching to x=1000.
    expect(ctx.fillRect).toHaveBeenCalledWith(780, 88.5, 220, 3);
  });

  it("draws nothing for a bar the series could not place", () => {
    const primitive = new TimeProfilePrimitive(COLORS);
    attach(primitive, () => null);
    primitive.setBars([{ price: 100, count: 10, isPointOfControl: true }]);

    const { target, ctx } = fakeTarget(1000);
    primitive.paneViews()[0]?.renderer()?.draw(target);

    expect(ctx.fillRect).not.toHaveBeenCalled();
  });
});
