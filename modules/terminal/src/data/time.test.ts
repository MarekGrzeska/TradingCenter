import { describe, expect, it } from "vitest";
import { parseIsoToEpochSeconds } from "./time";

describe("parseIsoToEpochSeconds", () => {
  // Shape matches what capital-gateway's mapper produces (mapping.py::_candle_ts):
  // ISO with an explicit `Z`. Confirming this against a real demo response is
  // task 8.2, run against a live account — this fixture is a synthetic instant,
  // computed independently below rather than trusted by eye.
  it("parses a UTC-marked gateway timestamp to the correct epoch second", () => {
    expect(parseIsoToEpochSeconds("2026-08-07T14:35:00Z")).toBe(1786113300);
  });

  it("treats an explicit non-zero offset as that offset, not local time", () => {
    // Same instant as the fixture above, spelled with a +02:00 offset instead
    // of Z — this is what would break if the parser assumed the local
    // timezone whenever a string wasn't literally "Z"-suffixed.
    expect(parseIsoToEpochSeconds("2026-08-07T16:35:00+02:00")).toBe(1786113300);
  });

  it("floors to the second, discarding fractional milliseconds", () => {
    expect(parseIsoToEpochSeconds("2026-08-07T14:35:00.999Z")).toBe(1786113300);
  });

  it("throws a descriptive error on an unparseable string", () => {
    expect(() => parseIsoToEpochSeconds("not-a-date")).toThrow(RangeError);
  });
});
