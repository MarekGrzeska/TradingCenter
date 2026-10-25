import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ReportPanel } from "./ReportPanel";
import { RunForm } from "./RunForm";
import type { CostProfile, Report, Run, StrategiesApi } from "./strategiesApi";

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

function form(client: StrategiesApi) {
  render(
    <RunForm api={client} strategyId={7} revision={4} symbol="US100" params={{}} maxMinuteBars={1_500_000} onQueued={() => {}} />,
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
