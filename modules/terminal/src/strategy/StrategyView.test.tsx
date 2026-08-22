import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MarketDataError } from "../data/types";
import { StrategyView } from "./StrategyView";
import type { Decision, Strategy, StrategyApi, Watch } from "./strategyApi";

/**
 * The tab from the operator's seat, and the claim it exists to make: **the refusals are
 * the screen**. A strategy worth running says no to most bars, so a tab that showed only
 * setups would be blank on exactly the day somebody asks why nothing happened.
 *
 * The other thing asserted here is that the three kinds of no stay apart. They have three
 * different remedies, and flattening them into "no signal" is the mistake this column was
 * added to prevent.
 */

const STRATEGY: Strategy = {
  id: "baseline_ma_cross",
  name: "Baseline · moving-average cross",
  description: "the floor every other strategy has to beat",
  resolution: "HOUR",
  candles: 300,
  facts: [],
  params: [
    { name: "fast_period", type: "int", default: 20, min: 2, max: 200 },
    { name: "stop_atr", type: "float", default: 2, min: 0.5, max: 6 },
  ],
};

const WATCH: Watch = {
  id: 1,
  strategyId: "baseline_ma_cross",
  symbol: "US100",
  parameterSetId: 5,
  active: true,
  createdAt: new Date("2026-08-22T09:00:00Z"),
};

function decision(overrides: Partial<Decision> = {}): Decision {
  return {
    id: 1,
    strategyId: "baseline_ma_cross",
    symbol: "US100",
    parameterSetId: 5,
    asOf: new Date("2026-08-22T10:00:00Z"),
    action: "no_trade",
    reason: "the fast average did not cross above the slow one on this bar",
    reasonKind: "strategy",
    direction: null,
    entry: null,
    stop: null,
    target: null,
    rr: null,
    score: null,
    features: {},
    createdAt: new Date("2026-08-22T11:00:00Z"),
    ...overrides,
  };
}

function fakeApi(overrides: Partial<StrategyApi> = {}): StrategyApi {
  return {
    listStrategies: vi.fn().mockResolvedValue([STRATEGY]),
    readStrategy: vi.fn().mockResolvedValue(STRATEGY),
    listWatches: vi.fn().mockResolvedValue([WATCH]),
    startWatch: vi.fn().mockResolvedValue(WATCH),
    setWatchActive: vi.fn().mockResolvedValue({ ...WATCH, active: false }),
    listParameterSets: vi.fn().mockResolvedValue([]),
    addParameterSet: vi.fn().mockResolvedValue({}),
    listDecisions: vi.fn().mockResolvedValue([decision()]),
    readDecision: vi.fn().mockResolvedValue(decision()),
    listBacktests: vi.fn().mockResolvedValue([]),
    readBacktest: vi.fn().mockResolvedValue({}),
    ...overrides,
  } as StrategyApi;
}

describe("the refusals are the screen", () => {
  it("shows them without being asked to", async () => {
    const api = fakeApi();

    render(<StrategyView api={api} />);

    expect(await screen.findByText(/did not cross/)).toBeInTheDocument();
    // No `action` filter: asking for setups alone is what would make this blank.
    expect(api.listDecisions).toHaveBeenCalledWith(expect.anything(), undefined);
  });

  it("tells a gap in the data apart from the strategy saying no", async () => {
    const api = fakeApi({
      listDecisions: vi.fn().mockResolvedValue([
        decision({ id: 1, reasonKind: "strategy" }),
        decision({
          id: 2,
          reasonKind: "coverage",
          reason: "the archive has not verified 2026-08-01–2026-08-02",
        }),
      ]),
    });

    render(<StrategyView api={api} />);

    // Two different words, because the two have different remedies: one is answered by
    // fetching history, the other by reading the strategy.
    expect(await screen.findByText("strategia")).toBeInTheDocument();
    expect(screen.getByText("brak danych")).toBeInTheDocument();
  });

  it("shows a setup's levels where a refusal has none", async () => {
    const api = fakeApi({
      listDecisions: vi.fn().mockResolvedValue([
        decision({
          id: 3,
          action: "trade",
          reasonKind: null,
          direction: "long",
          entry: 100.5,
          stop: 98.5,
          target: 106.5,
          rr: 3,
        }),
      ]),
    });

    render(<StrategyView api={api} />);

    expect(await screen.findByText("long")).toBeInTheDocument();
    expect(screen.getByText("100.50 / 98.50")).toBeInTheDocument();
    expect(screen.getByText("3.00R")).toBeInTheDocument();
  });
});

describe("when there is nothing yet", () => {
  it("says no pair is watched and what that means", async () => {
    // The state the platform is actually in on the day this screen ships: an empty list
    // with no explanation would read as a broken tab.
    const api = fakeApi({
      listWatches: vi.fn().mockResolvedValue([]),
      listDecisions: vi.fn().mockResolvedValue([]),
    });

    render(<StrategyView api={api} />);

    expect(await screen.findByTestId("nothing-watched")).toHaveTextContent(
      /Żadna para nie jest obserwowana/,
    );
  });
});

describe("when the module will not answer", () => {
  it("a refusal is not shown as an empty catalogue", async () => {
    const api = fakeApi({
      listStrategies: vi
        .fn()
        .mockRejectedValue(new MarketDataError("refused", "this caller has no access to rest")),
    });

    render(<StrategyView api={api} />);

    expect(await screen.findByText(/no access to rest/)).toBeInTheDocument();
  });
});

describe("stopping a watch", () => {
  it("flips it without touching what it decided", async () => {
    const api = fakeApi();

    render(<StrategyView api={api} />);
    await userEvent.click(await screen.findByRole("button", { name: "zatrzymaj" }));

    await waitFor(() => expect(api.setWatchActive).toHaveBeenCalledWith(1, false, expect.anything()));
    // Nothing on this screen deletes a decision, and the word on the button says "stop".
    expect(api.listDecisions).toHaveBeenCalled();
  });
});
