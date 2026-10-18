import { describe, expect, it } from "vitest";
import type { Catalog, Rule, RuleInput } from "./alertsApi";
import {
  argumentFields,
  attributeKind,
  blankForm,
  defectsFor,
  describeSource,
  formFrom,
  formProblem,
  inputFrom,
  opsFor,
  previewOf,
  statusOf,
  warnings,
} from "./present";

/**
 * The rules about what a form may offer and what it sends, without drawing one: which comparison an attribute of each kind
 * can take, which fields a tool's arguments make, that what the form builds is what the draft filled it from, and the words
 * a rule is described in.
 */

const CATALOG: Catalog = {
  tools: [
    {
      name: "get_last_price",
      description: "What a pair costs now.",
      source: "market-data",
      arguments: {
        properties: { symbol: { type: "string" }, resolution: { anyOf: [{ type: "string" }, { type: "null" }] } },
        required: ["symbol"],
      },
      numberFields: ["close", "age_seconds"],
    },
  ],
  eventTypes: [
    {
      name: "youtube.film.read",
      description: "A film the model read",
      attributes: {
        channel: { type: "string" },
        impact_score: { type: "integer" },
        instruments: { type: "array", items: { type: "string" } },
        simulated: { type: "boolean" },
      },
      seen: { channel: ["Gold Talk", "Macro"] },
    },
  ],
  recipients: [
    { name: "phone", bot: "alerts_bot", receives: true },
    { name: "tablet", bot: "alerts_bot", receives: false },
  ],
  gateway: true,
  minIntervalSeconds: 30,
  symbols: ["EURUSD", "XAUUSD"],
  drafting: true,
};

const PRICE: RuleInput = {
  name: "EURUSD powyżej 1,10",
  source: {
    kind: "condition",
    toolName: "get_last_price",
    arguments: { symbol: "EURUSD" },
    fieldPath: "close",
    comparison: "gt",
    threshold: "1.10",
    pollIntervalSeconds: 60,
  },
  destination: "phone",
  template: "",
  cooldownSeconds: 3600,
  mode: "repeat",
  maxPerHour: null,
  enabled: true,
};

const FILMS: RuleInput = {
  name: "Filmy z dwóch kanałów",
  source: {
    kind: "event",
    eventType: "youtube.film.read",
    filter: [
      { attribute: "channel", op: "in", value: ["Gold Talk", "Macro"] },
      { attribute: "impact_score", op: "gte", value: 7 },
      { attribute: "simulated", op: "eq", value: false },
    ],
  },
  destination: "phone",
  template: "{channel}: {impact_score}",
  cooldownSeconds: null,
  mode: "once",
  maxPerHour: 5,
  enabled: true,
};

function rule(overrides: Partial<Rule> = {}): Rule {
  return {
    ...PRICE,
    id: 1,
    disabledReason: null,
    defects: [],
    lastResult: false,
    lastCheckedAt: new Date("2026-10-18T12:00:00Z"),
    lastFiredAt: null,
    nextCheckAt: null,
    ...overrides,
  };
}

describe("what an attribute can be compared with", () => {
  it("offers a number the ordering, a text equality and membership, a flag only equality and a list only containment", () => {
    expect(opsFor(attributeKind({ type: "integer" }))).toContain("gte");
    expect(opsFor(attributeKind({ type: "string" }))).toEqual(["eq", "ne", "in"]);
    expect(opsFor(attributeKind({ type: "boolean" }))).toEqual(["eq", "ne"]);
    expect(opsFor(attributeKind({ type: "array", items: { type: "string" } }))).toEqual(["contains"]);
  });

  it("sees a number through a null, and offers nothing for what it does not know", () => {
    expect(attributeKind({ type: ["number", "null"] })).toBe("number");
    expect(attributeKind({ anyOf: [{ type: "string" }, { type: "null" }] })).toBe("string");
    expect(opsFor(attributeKind({}))).toEqual([]);
    expect(opsFor(attributeKind(undefined))).toEqual([]);
  });
});

describe("the arguments of a tool", () => {
  it("makes an instrument a choice among those the archive follows, and says which are required", () => {
    const fields = argumentFields(CATALOG.tools[0], CATALOG.symbols);

    expect(fields.find((one) => one.name === "symbol")).toMatchObject({ kind: "symbol", required: true, choices: ["EURUSD", "XAUUSD"] });
    expect(fields.find((one) => one.name === "resolution")).toMatchObject({ kind: "text", required: false });
  });

  it("falls back to typing the symbol where the archive could not be asked", () => {
    expect(argumentFields(CATALOG.tools[0], []).find((one) => one.name === "symbol")?.kind).toBe("text");
  });
});

describe("the form and the rule it builds", () => {
  it("builds back exactly the rule a price form was filled from", () => {
    expect(inputFrom(formFrom(PRICE, CATALOG), CATALOG)).toEqual(PRICE);
  });

  it("builds back an event rule with its ticked values, its number and its flag in their own types", () => {
    const built = inputFrom(formFrom(FILMS, CATALOG), CATALOG);

    expect(built.source).toEqual(FILMS.source);
    expect(built).toMatchObject({ mode: "once", maxPerHour: 5, cooldownSeconds: null });
  });

  it("saves a flag the operator left as the form showed it, which is yes", () => {
    const form = formFrom(FILMS, CATALOG);
    const blank = { attribute: "simulated", op: "eq" as const, value: "", picked: [] };

    const built = inputFrom({ ...form, terms: [blank] }, CATALOG);

    expect(built.source).toMatchObject({ filter: [{ attribute: "simulated", op: "eq", value: true }] });
  });

  it("leaves a number that is not one as it was typed, so the back end names it", () => {
    const form = { ...formFrom(PRICE, CATALOG), threshold: "wysoko", interval: "często" };

    const built = inputFrom(form, CATALOG);

    expect(built.source).toMatchObject({ threshold: "wysoko" });
  });

  it("starts from the first thing that exists and a recipient who receives", () => {
    const form = blankForm(CATALOG);

    expect(form).toMatchObject({ kind: "condition", tool: "get_last_price", fieldPath: "close", destination: "phone" });
    expect(Number(form.interval)).toBeGreaterThanOrEqual(CATALOG.minIntervalSeconds);
  });

  it("asks for a name, a recipient and a threshold before it can be saved, and for nothing else", () => {
    const blank = blankForm(CATALOG);

    expect(formProblem(blank)).toMatch(/Nazwij/);
    expect(formProblem({ ...blank, name: "x", destination: "" })).toMatch(/kogo/);
    expect(formProblem({ ...blank, name: "x", threshold: "" })).toMatch(/próg/);
    expect(formProblem({ ...blank, name: "x", threshold: "1" })).toBeNull();
  });
});

describe("the preview of a message", () => {
  it("fills a price rule with its own words and the threshold as the example value", () => {
    const form = { ...formFrom(PRICE, CATALOG), template: "{rule}: {symbol} {comparison} {threshold}" };

    expect(previewOf(form, CATALOG)).toBe("EURUSD powyżej 1,10: EURUSD powyżej 1.10");
  });

  it("uses the first value an attribute has had, and reaches into nothing", () => {
    const form = { ...formFrom(FILMS, CATALOG), template: "{channel} {x.__class__}!" };

    expect(previewOf(form, CATALOG)).toBe("Gold Talk !");
  });

  it("says the producer's own words for an event with no template", () => {
    expect(previewOf({ ...formFrom(FILMS, CATALOG), template: "" }, CATALOG)).toBe("‹treść od producenta›");
  });
});

describe("how a rule is described", () => {
  it("says a price rule in one line with its rhythm, and an event rule with its terms", () => {
    expect(describeSource(PRICE.source)).toBe("get_last_price(symbol=EURUSD).close powyżej 1.10 · co 60 s");
    expect(describeSource(FILMS.source)).toContain("youtube.film.read — gdy channel jest jednym z Gold Talk, Macro");
    expect(describeSource({ kind: "event", eventType: "teams.run.finished", filter: [] })).toBe("teams.run.finished — każde");
  });

  it("tells a working rule from a switched-off one, a wrong one and one that cannot read its value", () => {
    expect(statusOf(rule())).toEqual({ label: "działa", tone: "ok" });
    expect(statusOf(rule({ enabled: false, disabledReason: "fired" }))).toEqual({ label: "wyłączona — fired", tone: "muted" });
    expect(statusOf(rule({ defects: [{ field: "destination", message: "gone" }] })).tone).toBe("critical");
    expect(statusOf(rule({ lastResult: null })).tone).toBe("warning");
    expect(statusOf(rule({ lastCheckedAt: null })).label).toBe("jeszcze nie sprawdzona");
  });

  it("finds the reasons that belong to a field and its parts, and not its neighbours", () => {
    const defects = [
      { field: "source.filter.1.value", message: "a" },
      { field: "source.filter.10.value", message: "b" },
      { field: "destination", message: "c" },
    ];

    expect(defectsFor(defects, "source.filter.1").map((one) => one.message)).toEqual(["a"]);
  });
});

describe("what the package cannot do", () => {
  const fine = { delivering: true, readingValues: true, drafting: true, clock: { ran: true, ageSeconds: 4, expectedSeconds: 5 } };

  it("says nothing while everything works", () => {
    expect(warnings(fine)).toEqual([]);
  });

  it("names a missing door, missing tools and a clock that has stopped", () => {
    const found = warnings({ ...fine, delivering: false, readingValues: false, clock: { ran: true, ageSeconds: 60, expectedSeconds: 5 } });

    expect(found).toHaveLength(3);
    expect(found.join(" ")).toMatch(/bramy Telegrama/);
    expect(found.join(" ")).toMatch(/Zegar nie tyka/);
  });
});
