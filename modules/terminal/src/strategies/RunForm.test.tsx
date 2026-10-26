import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ReportPanel } from "./ReportPanel";
import { RunForm } from "./RunForm";
import type { CostProfile, Report, Run, StrategiesApi, Trade } from "./strategiesApi";

// The price chart is the library's canvas; what matters here is which levels the report asks it to draw.
const drawn = vi.hoisted(() => ({ levels: [] as { title?: string }[] }));
vi.mock("../chart/Chart", () => ({
  Chart: (props: { levels: { title?: string }[] }) => {
    drawn.levels = props.levels;
    return null;
  },
}));

/** The run form's costs from the operator's seat: read off capital.com with nothing typed, or left out on purpose. */

const BROKER: CostProfile = {
  costs: { spread: 0.3, slippage: 0, overnight_long: 0.000151992, overnight_short: -0.000069792, rollover_hour: 21 },
  source: "broker",
  fetchedAt: new Date("2026-10-25T09:00:00Z"),
};

function api(overrides: Partial<StrategiesApi> = {}): StrategiesApi {
  return {
    costs: vi.fn(async () => null),
    costsFromBroker: vi.fn(async () => BROKER),
    enqueue: vi.fn(async () => 11),
    ...overrides,
  } as unknown as StrategiesApi;
}

function form(client: StrategiesApi, execution = "MINUTE", maxExecutionBars = 1_500_000) {
  render(
    <RunForm
      api={client}
      strategyId={7}
      revision={4}
      symbol="US100"
      params={{}}
      execution={execution}
      maxExecutionBars={maxExecutionBars}
      onQueued={() => {}}
    />,
  );
}

describe("RunForm", () => {
  it("fills an instrument without a profile from capital.com and runs with nothing typed", async () => {
    const client = api();
    form(client);

    expect(await screen.findByText(/z capital\.com, pobrane 2026-10-25/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Spread/)).toHaveValue("0.3");
    await userEvent.click(screen.getByRole("button", { name: "Uruchom backtest" }));

    await waitFor(() => expect(client.enqueue).toHaveBeenCalled());
    // Unchanged costs are the profile's, so the package records where they came from.
    expect(vi.mocked(client.enqueue).mock.calls[0][0]).toMatchObject({ costs: null, withoutCosts: false });
  });

  it("runs without costs only when asked, and says what that leaves out", async () => {
    const client = api({ costsFromBroker: vi.fn(async () => Promise.reject(new Error("the broker did not answer"))) });
    form(client);
    await screen.findByText(/capital\.com nie podał kosztów/);

    await userEvent.click(screen.getByRole("checkbox", { name: "Bez kosztów" }));
    expect(screen.getByText(/będzie nierealistyczny/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Uruchom backtest" }));

    await waitFor(() => expect(client.enqueue).toHaveBeenCalled());
    expect(vi.mocked(client.enqueue).mock.calls[0][0]).toMatchObject({ costs: null, withoutCosts: true });
  });
});

describe("RunForm's ceiling", () => {
  // The default range is twelve months: 525,600 minutes, 105,120 five-minute candles.
  it.each([
    ["MINUTE", true],
    ["MINUTE_5", false],
  ])("counts candles of the %s series the strategy is settled on", async (execution, over) => {
    form(api(), execution, 200_000);
    await screen.findByText(/z capital\.com, pobrane/);

    expect(screen.queryByText(/skróć zakres/) !== null).toBe(over);
  });
});

describe("ReportPanel", () => {
  it("marks a run without costs and names where the costs came from", async () => {
    const report = {
      trades: 0, no_trades: true, costs: { spread: 0, slippage: 0, financing: 0 },
      benchmarks: { buy_and_hold: null, random_entry: null }, annualisation: "365 dni", equity: null,
      costs_source: "none", costs_fetched_at: null, without_costs: true,
    } as unknown as Report;
    const run = {
      id: 11, revision: 4, status: "done", from: new Date(), to: new Date(), engineVersion: 2,
      request: { costs: {} }, report, provenance: {},
    } as unknown as Run;
    const client = api({ run: vi.fn(async () => run), trades: vi.fn(async () => ({ total: 0, trades: [] })) });
    render(<ReportPanel api={client} runId={11} symbol="US100" timeframe="HOUR" />);

    expect(await screen.findByRole("note")).toHaveTextContent("wynik pomija spread, poślizg i finansowanie");
    expect(screen.getByText(/koszty bez kosztów/)).toBeInTheDocument();
  });
});


describe("A trade without a stop", () => {
  it("is drawn without a stop line and reads its result in percent, not in R", async () => {
    const report = {
      trades: 1, no_trades: false, costs: { spread: 0, slippage: 0, financing: 0 },
      benchmarks: { buy_and_hold: null, random_entry: null }, annualisation: "365 dni", equity: null,
      costs_source: "broker", costs_fetched_at: null, without_costs: false, margin_factor: 0.05,
    } as unknown as Report;
    const run = {
      id: 12, revision: 1, status: "done", from: new Date(), to: new Date(), engineVersion: 3,
      request: { costs: {} }, report, provenance: {},
    } as unknown as Run;
    const trade: Trade = {
      seq: 0, side: "long", entryTime: new Date("2026-07-02T13:35:00Z"), entryPrice: 20_000,
      exitTime: new Date("2026-07-02T19:55:00Z"), exitPrice: 20_300, units: 0.5, initialStop: null, resultR: null,
      resultMoney: 150, resultPct: 0.015, maePct: -0.002, costs: {}, exitReason: "when", pessimistic: false,
    };
    const client = api({ run: vi.fn(async () => run), trades: vi.fn(async () => ({ total: 1, trades: [trade] })) });
    render(<ReportPanel api={client} runId={12} symbol="US100" timeframe="MINUTE_5" />);

    const row = (await screen.findByRole("table", { name: "Transakcje" })).querySelector("tbody tr") as HTMLElement;
    await userEvent.click(row);

    expect(drawn.levels.map((l) => l.title)).toEqual(["wejście #0", "wyjście"]);
    expect(row).toHaveTextContent("1,5%");
    expect(row).toHaveTextContent("—");
  });
});

describe("Downloading a run's trades", () => {
  const report = {
    trades: 450, no_trades: false, costs: { spread: 0, slippage: 0, financing: 0 },
    benchmarks: { buy_and_hold: null, random_entry: null }, annualisation: "365 dni", equity: null,
    costs_source: "broker", costs_fetched_at: null, without_costs: false,
  } as unknown as Report;
  const run = {
    id: 14, revision: 1, status: "done", from: new Date(), to: new Date(), engineVersion: 4,
    request: { costs: {} }, report, provenance: {},
  } as unknown as Run;
  const trade: Trade = {
    seq: 200, side: "long", entryTime: new Date("2026-07-02T13:35:00Z"), entryPrice: 100,
    exitTime: new Date("2026-07-02T19:55:00Z"), exitPrice: 101, units: 1, initialStop: null, resultR: null,
    resultMoney: 1, resultPct: 0.001, maePct: 0, costs: {}, exitReason: "when", pessimistic: false,
  };

  function panel(overrides: Partial<StrategiesApi>) {
    const client = api({
      run: vi.fn(async () => run),
      trades: vi.fn(async () => ({ total: 450, trades: [trade] })),
      ...overrides,
    });
    render(<ReportPanel api={client} runId={14} symbol="US100" timeframe="MINUTE_5" />);
    return client;
  }

  it("saves the whole run, whatever page of the table is open", async () => {
    const file = new Blob(["seq\n"], { type: "text/csv" });
    const clicked: string[] = [];
    vi.stubGlobal("URL", { createObjectURL: () => "blob:trades", revokeObjectURL: () => {} });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push(this.download);
    });
    const client = panel({ downloadTrades: vi.fn(async () => file) });
    await userEvent.click(await screen.findByRole("button", { name: "›" }));
    await userEvent.click(await screen.findByRole("button", { name: "Pobierz transakcje (CSV)" }));

    expect(client.downloadTrades).toHaveBeenCalledWith(14, expect.anything());
    expect(clicked).toEqual(["run-14-trades.csv"]);
    expect(screen.getByRole("table", { name: "Transakcje" })).toBeInTheDocument();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("says why it could not, and leaves the table as it was", async () => {
    panel({ downloadTrades: vi.fn(async () => Promise.reject(new Error("serwer nie odpowiada"))) });
    await userEvent.click(await screen.findByRole("button", { name: "Pobierz transakcje (CSV)" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("serwer nie odpowiada");
    expect(screen.getByRole("table", { name: "Transakcje" })).toBeInTheDocument();
  });
});
