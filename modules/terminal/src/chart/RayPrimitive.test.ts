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
    // On a plate rather than straight on the chart: the caption sits above the line, and
    // the plate under it is what keeps it readable over the wicks (`terminal-chart` spec,
    // "Etykieta MUST być czytelna nad świecami").
    expect(ctx.fillRect).toHaveBeenCalledWith(40, 73.5, 26, 14);
    expect(ctx.fillText).toHaveBeenCalledWith("PDH", 44, 80.5);
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

describe("RayPrimitive — who drew it (terminal-chart spec, terminal-chart-objects)", () => {
  it("draws an operator's level heavier and unbroken, an indicator's thin and dashed", () => {
    // Weight is what carries authorship, because a chart with eight hues on it gives
    // nobody a way to remember which belong to which group (design.md, "Rysunek cięższy
    // od wskaźnika").
    const drawn = new RayPrimitive("#abc", { weight: "drawing", objectId: "3" });
    attach(drawn, 40, 90);
    drawn.setLevels([{ time: 100 as Time, price: 21000, label: null }]);
    const drawnTarget = fakeTarget(200);
    drawn.paneViews()[0]?.renderer()?.draw(drawnTarget.target);
    expect(drawnTarget.ctx.lineWidth).toBe(2);
    expect(drawnTarget.ctx.setLineDash).toHaveBeenCalledWith([]);

    const computed = new RayPrimitive("#abc");
    attach(computed, 40, 90);
    computed.setLevels([{ time: 100 as Time, price: 21000, label: null }]);
    const computedTarget = fakeTarget(200);
    computed.paneViews()[0]?.renderer()?.draw(computedTarget.target);
    expect(computedTarget.ctx.lineWidth).toBe(1);
    expect(computedTarget.ctx.setLineDash).toHaveBeenCalledWith([4, 4]);
  });

  it("keeps the caption on screen for a level starting off the left edge", () => {
    // `terminal-chart` spec, "Obiekt zaczynający się poza widokiem": a line crossing the
    // screen with no caption is a stroke nothing is known about.
    const ray = new RayPrimitive("#abc", { weight: "drawing", objectId: "3" });
    attach(ray, -500, 90);
    ray.setLevels([{ time: 1 as Time, price: 21000, label: "PDH" }]);

    const { target, ctx } = fakeTarget(200);
    ray.paneViews()[0]?.renderer()?.draw(target);

    expect(ctx.fillText).toHaveBeenCalledWith("PDH", 4, 80.5);
  });
});

describe("RayPrimitive — the price at the axis (terminal-chart spec)", () => {
  function drawnRay(price: number, currentPrice: number | null) {
    const ray = new RayPrimitive("#abc", {
      weight: "drawing",
      objectId: "3",
      palette: { onFill: "#000", support: "#up", resistance: "#down" },
    });
    attach(ray, 40, 90);
    ray.setLevels([{ time: 100 as Time, price, label: null }]);
    ray.setCurrentPrice(currentPrice);
    return ray;
  }

  it("says the price, coloured by the side of the market it sits on", () => {
    // The line says which object this is; the label says what it is (design.md, "Kolor:
    // linia z palety rysunków, etykieta przy osi kolorowana rolą").
    expect(drawnRay(21000, 21500).priceAxisViews()[0].backColor()).toBe("#up");
    expect(drawnRay(21900, 21500).priceAxisViews()[0].backColor()).toBe("#down");
    expect(drawnRay(21000, 21500).priceAxisViews()[0].text()).toBe("21000");
  });

  it("takes the line's own colour when the chart has drawn no candle yet", () => {
    // Nothing to be above or below, so no side to claim.
    expect(drawnRay(21000, null).priceAxisViews()[0].backColor()).toBe("#abc");
  });

  it("leaves the axis alone for an indicator's own levels", () => {
    // `level_clusters` on this chart would otherwise be an axis of nothing else.
    const computed = new RayPrimitive("#abc");
    attach(computed, 40, 90);
    computed.setLevels([{ time: 100 as Time, price: 21000, label: null }]);
    expect(computed.priceAxisViews()).toEqual([]);
  });
});

describe("RayPrimitive — clicking into it (terminal-chart-objects spec)", () => {
  function drawnRay() {
    const ray = new RayPrimitive("#abc", { weight: "drawing", objectId: "42" });
    attach(ray, 40, 90);
    ray.setLevels([{ time: 100 as Time, price: 21000, label: null }]);
    return ray;
  }

  it("answers with the drawing's own id, and asks for a pointer", () => {
    expect(drawnRay().hitTest(120, 90)).toEqual({
      externalId: "42",
      zOrder: "normal",
      cursorStyle: "pointer",
    });
  });

  it("counts a click a few pixels off the line as a click into it", () => {
    expect(drawnRay().hitTest(120, 93)?.externalId).toBe("42");
  });

  it("does not answer for a click further away than the tolerance", () => {
    expect(drawnRay().hitTest(120, 110)).toBeNull();
  });

  it("does not answer left of where the level starts", () => {
    expect(drawnRay().hitTest(10, 90)).toBeNull();
  });

  it("never answers for an indicator's own level", () => {
    // What a click picks out is an object somebody drew, not a reading.
    const computed = new RayPrimitive("#abc");
    attach(computed, 40, 90);
    computed.setLevels([{ time: 100 as Time, price: 21000, label: null }]);
    expect(computed.hitTest(120, 90)).toBeNull();
  });
});
