import { describe, expect, it } from "vitest";
import { stopKind, stopLabel } from "./stopReason";

/**
 * `terminal-teams`, "Zatrzymanie z powodu granicy zleceń jest pokazane jako takie".
 *
 * The sentences are the module's own — copied here from `runner/trading.py` and
 * `runner/cost.py` rather than invented, which is what makes this a test of the coupling
 * rather than of a regex.
 */
const ORDERS_PER_RUN =
  "the run's order limit was reached: 2 of 2 allowed placed. The next order was not sent.";
const ORDERS_PER_DAY =
  "this team's daily order limit is used up: 5 of 5 allowed placed today. No run was started.";
const RUN_COST =
  "the run's cost limit was reached: 0.5 spent of 0.5 allowed. The next model call was not made.";
const DAILY_COST =
  "this team's daily cost limit is used up: 2 spent today of 2 allowed. No run was started.";

describe("why a run stopped", () => {
  it("reads an order ceiling as orders", () => {
    expect(stopKind(ORDERS_PER_RUN)).toBe("orders");
    expect(stopKind(ORDERS_PER_DAY)).toBe("orders");
  });

  it("reads a cost ceiling as cost", () => {
    expect(stopKind(RUN_COST)).toBe("cost");
    expect(stopKind(DAILY_COST)).toBe("cost");
  });

  it("does not read one ceiling as the other", () => {
    // The whole requirement in one assertion: an operator reads "cost" and buys more
    // budget, reads "orders" and learns their team wanted to trade more than allowed.
    expect(stopKind(ORDERS_PER_RUN)).not.toBe(stopKind(RUN_COST));
    expect(stopLabel(stopKind(ORDERS_PER_RUN))).not.toBe(stopLabel(stopKind(RUN_COST)));
  });

  it("reads the time limit and an interruption as themselves", () => {
    expect(stopKind("the run exceeded its time limit")).toBe("time");
    expect(stopKind("the operator interrupted the run")).toBe("interrupted");
  });

  it("leaves a sentence it does not recognise unlabelled rather than guessing", () => {
    expect(stopKind("the run failed: something nobody has written yet")).toBe("other");
    expect(stopLabel("other")).toBeNull();
  });

  it("has nothing to say about a run that simply finished", () => {
    expect(stopKind(null)).toBe("other");
  });
});
