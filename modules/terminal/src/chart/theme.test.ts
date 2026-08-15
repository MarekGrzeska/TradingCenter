import { describe, expect, it } from "vitest";
import {
  INDICATOR_LINE_TOKENS,
  indicatorColorFromToken,
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
