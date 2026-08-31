import { describe, expect, it } from "vitest";
import { headlineMarket, marketsForDisplay } from "./ordering";
import { aMarket, anEvent, anOutcome } from "../test/builders";

const priced = (id: number, price: number | null) =>
  aMarket({ id, outcomes: [anOutcome({ id: id * 10, price })] });

describe("the order markets are shown in", () => {
  it("puts the likeliest leading outcome first", () => {
    const ordered = marketsForDisplay([priced(1, 0.2), priced(2, 0.9), priced(3, 0.5)]);
    expect(ordered.map((market) => market.id)).toEqual([2, 3, 1]);
  });

  it("puts a market with no collected price last, not first", () => {
    const ordered = marketsForDisplay([priced(1, null), priced(2, 0.1)]);
    expect(ordered.map((market) => market.id)).toEqual([2, 1]);
  });

  it("sinks resolved markets below every open one, however high they priced", () => {
    const resolved = aMarket({
      id: 1,
      resolvedOutcome: "Yes",
      outcomes: [anOutcome({ price: 1 })],
    });
    const ordered = marketsForDisplay([resolved, priced(2, 0.05)]);
    expect(ordered.map((market) => market.id)).toEqual([2, 1]);
  });

  it("reads a market by the outcome the provider lists first, not by the highest one", () => {
    const market = aMarket({
      id: 1,
      outcomes: [anOutcome({ id: 1, name: "Yes", price: 0.3 }), anOutcome({ id: 2, name: "No", price: 0.7 })],
    });
    const [first] = marketsForDisplay([market, priced(2, 0.5)]);
    expect(first.id).toBe(2);
  });
});

describe("the headline a collapsed card carries", () => {
  it("is the first market the open list would show", () => {
    const event = anEvent({ markets: [priced(1, 0.2), priced(2, 0.8)] });
    expect(headlineMarket(event)?.id).toBe(2);
  });

  it("is nothing for an event whose markets have not arrived", () => {
    expect(headlineMarket(anEvent({ markets: [] }))).toBeUndefined();
  });
});
