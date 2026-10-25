import { describe, expect, it } from "vitest";
import { offersInFormula } from "./completions";
import type { Language } from "./strategiesApi";

const LANGUAGE = {
  schema_version: 1, sections: [], constructions: [], series: {}, time: {}, constants: {}, position: {}, history: {},
  resolutions: [], functions: [], indicators: [], max_bars: 5000,
  sessions: { NEW_YORK: "America/New_York 09:30–16:00 local time, Monday to Friday; no exchange holidays" },
} as unknown as Language;

describe("offersInFormula", () => {
  it("offers the sessions a session function takes, with their hours", () => {
    expect(offersInFormula(LANGUAGE, {})).toContainEqual({
      label: "NEW_YORK",
      detail: "America/New_York 09:30–16:00 local time, Monday to Friday; no exchange holidays",
      kind: "constant",
    });
  });
});
