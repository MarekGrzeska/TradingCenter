/**
 * The node vocabulary, as the screen offers it.
 *
 * **The list of kinds is the module's, spelled here in Polish.** What a node *is* comes from
 * `contract.strategy.generated.ts` and is never restated — this file only says what each
 * kind is called on screen and what a freshly added one starts out as. A kind the module
 * grows and this file does not name simply does not appear in the picker, which is the safe
 * direction: the editor can lag the vocabulary, never lead it.
 *
 * Blanks are deliberately valid on their own. A half-built tree the module would refuse is
 * the ordinary state of an editor mid-thought, but a blank that could not even be
 * *serialized* would make the whole rule unreadable the moment somebody added a row.
 */

import type { ConditionNode, NumericNode } from "../strategyApi";

export type NumericKind = NumericNode["node"];
export type ConditionKind = ConditionNode["node"];

/** What each numeric kind is called, in the order a picker should offer it: the leaves an
 *  operator reaches for first, then the arithmetic that combines them. */
export const NUMERIC_LABELS: Record<NumericKind, string> = {
  const: "liczba",
  param: "parametr strategii",
  fact: "odczyt wskaźnika",
  bar: "cena świecy",
  arith: "działanie",
  call: "funkcja",
  previous: "o świecę wcześniej",
};

export const CONDITION_LABELS: Record<ConditionKind, string> = {
  compare: "porównanie",
  crossed: "przecięcie",
  logic: "spójnik",
  settled: "odczyty są policzone",
};

export const NUMERIC_KINDS = Object.keys(NUMERIC_LABELS) as NumericKind[];
export const CONDITION_KINDS = Object.keys(CONDITION_LABELS) as ConditionKind[];

export const ARITH_OPS = ["+", "-", "*", "/"] as const;
export const CALL_FNS = ["abs", "min", "max", "round"] as const;
export const COMPARE_OPS = ["<", "<=", ">", ">="] as const;
export const LOGIC_OPS = ["all", "any", "not"] as const;
export const BAR_FIELDS = ["open", "high", "low", "close"] as const;

export const LOGIC_LABELS: Record<(typeof LOGIC_OPS)[number], string> = {
  all: "wszystkie naraz",
  any: "którykolwiek",
  not: "nieprawda, że",
};

/** How many operands a kind may hold, so the editor knows whether to offer "dodaj". */
export function operandLimits(node: NumericNode | ConditionNode): { min: number; max: number } {
  if (node.node === "arith") return node.op === "-" || node.op === "/" ? { min: 2, max: 2 } : { min: 2, max: 8 };
  if (node.node === "call") {
    if (node.fn === "abs") return { min: 1, max: 1 };
    if (node.fn === "round") return { min: 2, max: 2 };
    return { min: 2, max: 8 };
  }
  if (node.node === "logic") return node.op === "not" ? { min: 1, max: 1 } : { min: 1, max: 8 };
  if (node.node === "settled") return { min: 1, max: 8 };
  return { min: 0, max: 0 };
}

export function blankNumeric(kind: NumericKind, firstFact?: string, firstParam?: string): NumericNode {
  switch (kind) {
    case "const":
      return { node: "const", value: 0 };
    case "param":
      return { node: "param", name: firstParam ?? "" };
    case "fact":
      return { node: "fact", key: firstFact ?? "", line: "", offset: 0 };
    case "bar":
      return { node: "bar", field: "close", offset: 0 };
    case "arith":
      return { node: "arith", op: "+", operands: [{ node: "const", value: 0 }, { node: "const", value: 0 }] };
    case "call":
      return { node: "call", fn: "min", operands: [{ node: "const", value: 0 }, { node: "const", value: 0 }] };
    case "previous":
      return { node: "previous", of: { node: "const", value: 0 } };
  }
}

export function blankCondition(
  kind: ConditionKind,
  firstFact?: string,
  firstParam?: string,
): ConditionNode {
  const left = blankNumeric("fact", firstFact, firstParam);
  switch (kind) {
    case "compare":
      return { node: "compare", op: ">", left, right: { node: "const", value: 0 } };
    case "crossed":
      return { node: "crossed", direction: "above", left, right: { node: "const", value: 0 } };
    case "logic":
      return {
        node: "logic",
        op: "all",
        operands: [{ node: "compare", op: ">", left, right: { node: "const", value: 0 } }],
      };
    case "settled":
      return { node: "settled", of: [left] };
  }
}

/** A rule with nothing in it that the module would not accept as shaped — one fact, one
 *  parameter and one setup, all of them obviously placeholders. */
export function blankRule(): import("../strategyApi").Rule {
  return {
    resolution: "HOUR",
    candles: 300,
    unsettled_reason: "odczyty jeszcze się nie ustabilizowały",
    no_setup_reason: "warunek wejścia nie zaszedł na tej świecy",
    facts: [],
    params: [],
    guards: [],
    setups: [
      {
        when: { node: "compare", op: ">", left: { node: "bar", field: "close", offset: 0 }, right: { node: "const", value: 0 } },
        direction: "long",
        entry: { node: "bar", field: "close", offset: 0 },
        stop: { node: "const", value: 0 },
        target: { node: "const", value: 0 },
        score: null,
        reason: "warunek wejścia zaszedł",
      },
    ],
    features: {},
  };
}
