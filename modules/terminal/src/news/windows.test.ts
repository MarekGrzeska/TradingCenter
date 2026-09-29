import { describe, expect, it } from "vitest";
import { DEFAULT_MINUTES, limitFor, windowName, WINDOWS } from "./windows";

describe("windows", () => {
  it("offers 5 min to 7 d, and defaults to one of them", () => {
    expect(WINDOWS.map((w) => w.label)).toEqual(["5 min", "15 min", "1 h", "4 h", "24 h", "7 d"]);
    expect(WINDOWS.map((w) => w.minutes)).toContain(DEFAULT_MINUTES);
  });

  it("names the window and asks for more headlines the longer it is", () => {
    expect(windowName(240)).toBe("ostatnie 4 h");
    expect(windowName(10080)).toBe("ostatnie 7 d");
    expect(limitFor(60)).toBe(300);
    expect(limitFor(1440)).toBe(1000);
  });
});
