import { describe, expect, it } from "vitest";
import { problemSpan } from "./jsonPaths";

const text = JSON.stringify(
  { name: "t", entries: [{ side: "long", when: '"x" == 1 and emaa(20) > 1' }], exits: { target: "1" } },
  null,
  2,
);

describe("problemSpan", () => {
  it("marks a name in a formula by the formula's own column, through the JSON's escapes", () => {
    // `emaa` is the formula's 14th character; in the text, the two escaped quotes before it are four.
    const span = problemSpan(text, "entries[0].when", 14);

    expect(text.slice(span.from, span.to)).toBe("emaa");
  });

  it("marks a field that is missing on the nearest value that is there", () => {
    const span = problemSpan(text, "exits.stop", null);

    expect(text.slice(span.from, span.to)).toBe('{\n    "target": "1"\n  }');
  });
});
