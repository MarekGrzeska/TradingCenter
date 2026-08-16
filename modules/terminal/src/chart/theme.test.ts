import { describe, expect, it } from "vitest";
import {
  DRAWING_LINE_TOKENS,
  INDICATOR_LINE_TOKENS,
  drawingColorFor,
  drawingColorFromToken,
  indicatorColorFromToken,
  isDrawingColorToken,
  isIndicatorColorToken,
  readChartColors,
} from "./theme";

describe("indicator colour tokens", () => {
  it("resolves every offered token to a colour", () => {
    const colors = readChartColors();
    for (const token of INDICATOR_LINE_TOKENS) {
      expect(indicatorColorFromToken(colors, token)).toMatch(/^#[0-9a-f]{6}$/i);
    }
  });

  it("resolves a token to the same colour the cycle draws at that position", () => {
    const colors = readChartColors();
    INDICATOR_LINE_TOKENS.forEach((token, index) => {
      expect(indicatorColorFromToken(colors, token)).toBe(colors.indicatorLines[index]);
    });
  });

  it("refuses a token the palette does not offer", () => {
    const colors = readChartColors();
    // What a slot saved against an older palette hands back — "assign one yourself",
    // never a line painted `undefined`.
    expect(indicatorColorFromToken(colors, "--color-indicator-99")).toBeNull();
    expect(indicatorColorFromToken(colors, "#3987e5")).toBeNull();
    expect(isIndicatorColorToken("--color-indicator-99")).toBe(false);
    expect(isIndicatorColorToken("--color-accent")).toBe(true);
  });

  it("treats no chosen colour as no colour, not as the first one", () => {
    expect(indicatorColorFromToken(readChartColors(), null)).toBeNull();
  });
});

describe("drawing colour tokens", () => {
  it("shares no colour with the indicator palette", () => {
    // The whole reason this palette exists: a drawn resistance in exactly EMA 200's
    // colour is an object that cannot be told from something else entirely
    // (`agent-chart-drawings` spec, "Paleta rysunków MUST być odrębna").
    const colors = readChartColors();
    const indicators = new Set(colors.indicatorLines);
    for (const drawn of colors.drawingLines) expect(indicators.has(drawn)).toBe(false);
    for (const token of DRAWING_LINE_TOKENS) {
      expect(isIndicatorColorToken(token)).toBe(false);
      expect(isDrawingColorToken(token)).toBe(true);
    }
  });

  it("resolves every offered token to a colour", () => {
    const colors = readChartColors();
    DRAWING_LINE_TOKENS.forEach((token, index) => {
      expect(drawingColorFromToken(colors, token)).toBe(colors.drawingLines[index]);
    });
  });

  it("still resolves an indicator token, for the objects drawn before this palette", () => {
    // The tool stopped offering these, but the rows saved with one are still on
    // instruments; forgetting them here would blank objects nobody removed (design.md,
    // "Paleta rysunków dokłada tokeny, nie odbiera starych").
    const colors = readChartColors();
    expect(drawingColorFromToken(colors, "--color-accent")).toBe(colors.indicatorLines[0]);
    expect(drawingColorFromToken(colors, "--color-down")).toBe(colors.indicatorLines[7]);
  });

  it("refuses a token neither palette knows, and no colour at all", () => {
    const colors = readChartColors();
    expect(drawingColorFromToken(colors, "--color-drawing-99")).toBeNull();
    expect(drawingColorFromToken(colors, null)).toBeNull();
  });

  it("gives one id one colour, whatever else is on the chart", () => {
    const colors = readChartColors();
    expect(drawingColorFor(7, colors)).toBe(drawingColorFor(7, colors));
    // The property the old position-in-the-list cycle did not have: an id's colour is a
    // function of the id alone, so removing a neighbour repaints nothing
    // (`terminal-chart` spec, "Kolor obiektu po usunięciu innego").
    const before = [4, 7, 11].map((id) => drawingColorFor(id, colors));
    const after = [7, 11].map((id) => drawingColorFor(id, colors));
    expect(after).toEqual(before.slice(1));
  });

  it("gives objects drawn one after another different colours", () => {
    const colors = readChartColors();
    const consecutive = [1, 2, 3, 4].map((id) => drawingColorFor(id, colors));
    expect(new Set(consecutive).size).toBe(4);
  });
});
