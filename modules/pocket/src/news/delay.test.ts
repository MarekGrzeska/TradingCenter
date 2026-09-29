import { describe, expect, it } from "vitest";
import { formatDelay, formatRange } from "./delay";

const measured = { delayMinSeconds: 180, delayMaxSeconds: 300, delayUnmeasured: null } as const;

describe("formatDelay", () => {
  it("shows both ends of a measured range", () => {
    expect(formatDelay(measured)).toBe("3–5 min");
  });

  it("keeps the unit on each end when they differ", () => {
    expect(formatRange(20, 300)).toBe("20 s–5 min");
    expect(formatRange(600, 7200)).toBe("10 min–2 h");
  });

  it("collapses equal ends", () => {
    expect(formatRange(180, 180)).toBe("3 min");
  });

  it.each([
    ["found_there", "found on first fetch"],
    ["no_publish_time", "no publish time"],
    ["publish_time_in_future", "source clock ahead"],
  ] as const)("says why there is no delay: %s", (reason, words) => {
    expect(formatDelay({ delayMinSeconds: null, delayMaxSeconds: null, delayUnmeasured: reason })).toBe(words);
  });
});
