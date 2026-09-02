import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MarketDataError } from "../data/types";
import type { Resolution, TrackedPair } from "../data/types";
import type { ArchiveAdmin } from "../data/source";
import { StrategyView } from "./StrategyView";
import type { Decision, Strategy, StrategyApi, Watch } from "./strategyApi";

/**
 * **The refusals are the screen**: a strategy worth running says no to most bars, so a tab of setups would be blank on
 * the day somebody asks why nothing happened. The three kinds of no stay apart, because they have three remedies.
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
  source: "code",
  revision: null,
};

const WATCH: Watch = {
  id: 1,
  strategyId: "baseline_ma_cross",
  symbol: "US100",
  parameterSetId: 5,
  active: true,
  createdAt: new Date("2026-08-22T09:00:00Z"),
  strategyRevisionId: null,
};

function decision(overrides: Partial<Decision> = {}): Decision {
  return {
    id: 1,
    strategyId: "baseline_ma_cross",
    symbol: "US100",
    parameterSetId: 5,
    strategyRevision: null,
    strategyRevisionId: null,
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

/** The archive, as this screen uses it: which instruments it collects, and nothing else. */
function pair(symbol: string, resolution: Resolution): TrackedPair {
  return {
    symbol,
    resolution,
    addedAt: 1786269600,
    collectFrom: 1786269600,
    earliestCandle: null,
    latestCandle: null,
    collection: "collecting",
    candleCount: 0,
    estimatedBytes: 0,
  };
}

function fakeAdmin(pairs: TrackedPair[] = [pair("US100", "HOUR")]): ArchiveAdmin {
  return { listPairs: vi.fn().mockResolvedValue(pairs) } as unknown as ArchiveAdmin;
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
    listDefinitions: vi.fn().mockResolvedValue([]),
    listRevisions: vi.fn().mockResolvedValue([]),
    addDefinition: vi.fn().mockResolvedValue({}),
    addRevision: vi.fn().mockResolvedValue({}),
    renameDefinition: vi.fn().mockResolvedValue({}),
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

describe("reading a decision", () => {
  const SNAPSHOT = {
    symbol: "US100",
    as_of: "2026-08-22T10:00:00+00:00",
    candles: [],
    values: {
      fast: {
        key: "fast",
        resolution: "HOUR",
        times: ["2026-08-22T09:00:00+00:00", "2026-08-22T10:00:00+00:00"],
        lines: { value: [101.2, 101.9] },
        markers: [],
        zones: [],
      },
    },
  };

  it("opens to the readings it stood on and the parameters it was computed with", async () => {
    const api = fakeApi({
      readDecision: vi
        .fn()
        .mockResolvedValue({ ...decision({ features: { spread: 0.7 } }), facts: SNAPSHOT }),
      listParameterSets: vi.fn().mockResolvedValue([
        {
          id: 5,
          strategyId: "baseline_ma_cross",
          version: 2,
          params: { fast_period: 20, stop_atr: 2 },
          createdAt: new Date("2026-08-22T09:00:00Z"),
        },
      ]),
    });

    render(<StrategyView api={api} />);
    await userEvent.click(await screen.findByTestId("decision-row"));

    const dialog = await screen.findByRole("dialog");
    // The version, not only the values — and the values, which are what a dispute is about.
    expect(within(dialog).getByTestId("decision-parameters")).toHaveTextContent("zestaw #5 · v2");
    expect(within(dialog).getByTestId("decision-parameters")).toHaveTextContent("fast_period = 20");
    expect(within(dialog).getByTestId("decision-features")).toHaveTextContent("spread = 0.7000");
    // The snapshot the platform kept, offset 0 first: what the rule called "now".
    const readings = await within(dialog).findByTestId("decision-readings");
    expect(within(readings).getAllByRole("row").map((row) => row.textContent)).toEqual([
      "−świecavalue",
      expect.stringMatching(/^0.*101\.90$/),
      expect.stringMatching(/^1.*101\.20$/),
    ]);
    expect(api.readDecision).toHaveBeenCalledWith(1, expect.anything());
  });

  it("keeps a detail it could not read beside the row that has the rest", async () => {
    const api = fakeApi({
      readDecision: vi
        .fn()
        .mockRejectedValue(new MarketDataError("unreachable", "strategy did not answer")),
    });

    render(<StrategyView api={api} />);
    await userEvent.click(await screen.findByTestId("decision-row"));

    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText(/did not answer/)).toBeInTheDocument();
    // The row's own facts still stand: the reason came with the list.
    expect(within(dialog).getByTestId("decision-verdict")).toHaveTextContent(/did not cross/);
  });

  it("offers nothing to do on the account from a setup", async () => {
    const api = fakeApi({
      listDecisions: vi
        .fn()
        .mockResolvedValue([
          decision({ action: "trade", reasonKind: null, direction: "long", entry: 100.5, stop: 98.5, target: 106.5, rr: 3 }),
        ]),
      readDecision: vi.fn().mockResolvedValue({ ...decision(), facts: {} }),
    });

    render(<StrategyView api={api} />);
    await userEvent.click(await screen.findByTestId("decision-row"));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByTestId("decision-levels")).toHaveTextContent("cel 106.50");
    // A setup is a reading. The only button in this dialog is the one that closes it.
    expect(within(dialog).getAllByRole("button").map((one) => one.getAttribute("aria-label"))).toEqual([
      "Close",
    ]);
  });
});

describe("backtest reports", () => {
  it("are read with their cost model, and never started from here", async () => {
    const api = fakeApi({
      listBacktests: vi.fn().mockResolvedValue([
        {
          id: 1,
          strategyId: "baseline_ma_cross",
          symbol: "US100",
          resolution: "HOUR",
          rangeFrom: new Date("2026-01-01T00:00:00Z"),
          rangeTo: new Date("2026-06-30T00:00:00Z"),
          params: { fast_period: 20, stop_atr: 2 },
          costs: { spread: 0.5, slippage: 0.1, commission_r: 0 },
          report: {
            metrics: { trades: 12, wins: 7, win_rate: 0.58, expectancy_r: 0.42, total_r: 5.04, max_drawdown_r: 2.1, unresolved: 1 },
            refusals: {},
            bars: 4300,
            strategy_revision: null,
          },
          ranAt: new Date("2026-08-01T12:00:00Z"),
        },
      ]),
    });

    render(<StrategyView api={api} />);

    const row = await screen.findByTestId("backtest-row");
    expect(row).toHaveTextContent("spread 0.5 · poślizg 0.1 · prowizja 0R");
    expect(row).toHaveTextContent("fast_period=20, stop_atr=2");
    expect(row).toHaveTextContent("0.42R");
    expect(screen.queryByRole("button", { name: /backtest|przebieg|uruchom/i })).toBeNull();
  });

  it("says what an empty list means", async () => {
    render(<StrategyView api={fakeApi()} />);

    expect(await screen.findByTestId("no-backtests")).toHaveTextContent(/komendą/);
  });

  it("keeps a refusal beside the list it refused", async () => {
    const api = fakeApi({
      listBacktests: vi
        .fn()
        .mockRejectedValue(new MarketDataError("refused", "this caller has no access to backtests")),
    });

    render(<StrategyView api={api} />);

    expect(await screen.findByText(/no access to backtests/)).toBeInTheDocument();
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

describe("starting a watch", () => {
  it("offers what the archive collects and sends the pair that was picked", async () => {
    const api = fakeApi({ listWatches: vi.fn().mockResolvedValue([]) });
    // Typed by hand, a symbol the archive does not collect is a watch that can only ever
    // record refusals — so the instrument is picked from what it does collect.
    const admin = fakeAdmin([pair("EURUSD", "MINUTE"), pair("US100", "MINUTE"), pair("US100", "HOUR")]);

    render(<StrategyView api={api} admin={admin} />);
    await userEvent.click(await screen.findByRole("button", { name: "Obserwuj parę" }));
    const instrument = await screen.findByRole("combobox", { name: "Instrument" });
    expect([...instrument.querySelectorAll("option")].map((option) => option.textContent)).toEqual([
      "EURUSD",
      "US100",
    ]);

    await userEvent.selectOptions(instrument, "US100");
    await userEvent.click(screen.getByRole("button", { name: "Zacznij" }));

    // No parameters: untouched fields mean the defaults, and resolving them here would
    // make this screen the author of values it only displayed.
    await waitFor(() =>
      expect(api.startWatch).toHaveBeenCalledWith(
        "baseline_ma_cross",
        "US100",
        expect.anything(),
        undefined,
      ),
    );
  });

  it("still starts when the catalogue arrives after the dialog does", async () => {
    // The failure this is here for: against a cold module the catalogue read takes seconds, and an operator who
    // opened the dialog inside that window got a select that filled itself and a "Zacznij" that never revived.
    let answer: (strategies: Strategy[]) => void = () => {};
    const api = fakeApi({
      listStrategies: vi.fn().mockReturnValue(
        new Promise<Strategy[]>((resolve) => {
          answer = resolve;
        }),
      ),
      listWatches: vi.fn().mockResolvedValue([]),
    });

    render(<StrategyView api={api} admin={fakeAdmin()} />);
    await userEvent.click(await screen.findByRole("button", { name: "Obserwuj parę" }));
    answer([STRATEGY]);

    // The instrument alone used to leave this dead: no strategy was selected, and none
    // could be.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Zacznij" })).not.toBeDisabled(),
    );
    await userEvent.click(screen.getByRole("button", { name: "Zacznij" }));

    await waitFor(() =>
      expect(api.startWatch).toHaveBeenCalledWith(
        "baseline_ma_cross",
        "US100",
        expect.anything(),
        undefined,
      ),
    );
  });

  it("keeps a refusal beside the question it answers", async () => {
    const api = fakeApi({
      listWatches: vi.fn().mockResolvedValue([]),
      startWatch: vi
        .fn()
        .mockRejectedValue(new MarketDataError("refused", "US100 is not in the archive")),
    });

    render(<StrategyView api={api} admin={fakeAdmin()} />);
    await userEvent.click(await screen.findByRole("button", { name: "Obserwuj parę" }));
    await userEvent.click(await screen.findByRole("button", { name: "Zacznij" }));

    expect(await screen.findByText(/not in the archive/)).toBeInTheDocument();
  });

  it("says an empty archive is why nothing can be started", async () => {
    // Not a dead dialog: this is the one state where the operator's next move is another
    // tab entirely.
    const api = fakeApi({ listWatches: vi.fn().mockResolvedValue([]) });

    render(<StrategyView api={api} admin={fakeAdmin([])} />);
    await userEvent.click(await screen.findByRole("button", { name: "Obserwuj parę" }));

    expect(await screen.findByText(/Archiwum nie zbiera żadnego instrumentu/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Zacznij" })).toBeDisabled();
  });
});
