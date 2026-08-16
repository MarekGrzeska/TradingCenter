/**
 * What stopped a run, as a kind rather than as a sentence.
 *
 * The module writes the sentence and the terminal shows it whole — it names the number,
 * which is what an operator actually acts on. This adds the one thing prose alone does
 * not give: a label that is *different* for a run stopped by its order count than for
 * one stopped by its cost ceiling, which is what `terminal-teams` requires ("Granica
 * zleceń jako przyczyna zatrzymania, odróżniona od kosztu"). The two mean opposite
 * things to whoever reads them — cost is an experiment that got expensive, orders is a
 * team that wanted to trade more than it was allowed, and the second is a result rather
 * than an accident.
 *
 * Read off the module's own words, the way `refusal.ts` reads its refusals. That couples
 * this to sentences written in `runner/cost.py` and `runner/trading.py`; the coupling is
 * deliberate and cheap, and `other` is what any sentence this does not recognise falls
 * to — the reason is still shown in full, only unlabelled.
 */
export type StopKind = "orders" | "cost" | "time" | "interrupted" | "other";

const PATTERNS: ReadonlyArray<[StopKind, RegExp]> = [
  // `RunOrderLimitReached` / `DailyOrderLimitReached` (`runner/trading.py`).
  ["orders", /order limit/i],
  // `RunCostLimitReached` / `DailyCostLimitReached` (`runner/cost.py`).
  ["cost", /cost limit/i],
  ["time", /time limit/i],
  ["interrupted", /interrupted/i],
];

export function stopKind(reason: string | null): StopKind {
  if (reason === null) return "other";
  for (const [kind, pattern] of PATTERNS) {
    if (pattern.test(reason)) return kind;
  }
  return "other";
}

/** A short word for the badge beside the reason. `other` has none — an unlabelled
 *  sentence reads better than one labelled "other". */
export function stopLabel(kind: StopKind): string | null {
  switch (kind) {
    case "orders":
      return "order limit";
    case "cost":
      return "cost limit";
    case "time":
      return "time limit";
    case "interrupted":
      return "interrupted";
    case "other":
      return null;
  }
}
