import { describe, expect, it } from "vitest";
import { PULL_THRESHOLD, pullOffset, shouldRefresh } from "./pull";

describe("the pull gesture", () => {
  it("moves nothing at all upwards — that is a scroll, not a request", () => {
    expect(pullOffset(-40)).toBe(0);
    expect(pullOffset(0)).toBe(0);
  });

  it("follows the thumb damped, so the bottom of the drag does not feel broken", () => {
    expect(pullOffset(40)).toBeLessThan(40);
    expect(pullOffset(40)).toBeGreaterThan(0);
  });

  it("stops following well before the screen could be dragged off", () => {
    expect(pullOffset(10_000)).toBe(PULL_THRESHOLD * 1.5);
  });

  it("asks for a read only past the threshold, so a flick past the top is not a request", () => {
    expect(shouldRefresh(PULL_THRESHOLD - 1)).toBe(false);
    expect(shouldRefresh(PULL_THRESHOLD)).toBe(true);
  });
});
