import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { useIndicatorCatalogue } from "../chart/indicators/useIndicatorCatalogue";
import type { IndicatorSource } from "../data/source";
import type { IndicatorCatalogue } from "../data/types";
import { DefinitionDialog } from "./DefinitionDialog";
import type { StrategyApi } from "./strategyApi";

/**
 * Where the pickers come from, and where the refusal lands. The first test is load-bearing: nothing in this screen
 * names an indicator, so one the archive grows appears with no change here.
 */

function catalogue(...ids: string[]): IndicatorCatalogue {
  return {
    algorithmVersion: 1,
    indicators: ids.map((id) => ({
      id,
      name: id.toUpperCase(),
      aliases: [],
      group: "averages",
      output: "lines" as const,
      params: [{ name: "period", type: "int" as const, default: 20, min: 2, max: 5000 }],
      lines: [{ key: id, label: id, style: null }],
      render: {
        pane: "price" as const,
        style: "line" as const,
        scale: "price" as const,
        autoscale: true,
        range: null,
        levels: [],
      },
      warmupKind: "fixed" as const,
    })),
  };
}

function fakeSource(answer: IndicatorCatalogue = catalogue("ema", "atr")): IndicatorSource {
  return {
    indicatorCatalogue: vi.fn().mockResolvedValue(answer),
  } as unknown as IndicatorSource;
}

function fakeApi(overrides: Partial<StrategyApi> = {}): StrategyApi {
  return {
    addDefinition: vi.fn().mockResolvedValue({}),
    addRevision: vi.fn().mockResolvedValue({}),
    ...overrides,
  } as unknown as StrategyApi;
}

describe("writing a rule", () => {
  it("offers whatever the archive announces, without naming any of it here", async () => {
    render(
      <DefinitionDialog
        client={fakeApi()}
        source={fakeSource(catalogue("ema", "supertrend"))}
        onClose={() => {}}
        onSaved={() => {}}
      />,
    );
    await userEvent.click(await screen.findByText("dodaj fakt"));

    const picker = screen.getByLabelText("Wskaźnik faktu 1");

    expect([...picker.querySelectorAll("option")].map((one) => one.textContent)).toEqual([
      "—",
      "EMA",
      "SUPERTREND",
    ]);
  });

  it("hands the module the rule as it was composed", async () => {
    const api = fakeApi();
    const saved = vi.fn();
    render(
      <DefinitionDialog
        client={api}
        source={fakeSource()}
        onClose={() => {}}
        onSaved={saved}
      />,
    );

    await userEvent.type(await screen.findByLabelText("Identyfikator"), "wybicie");
    await userEvent.type(screen.getByLabelText("Nazwa"), "Wybicie");
    await userEvent.click(screen.getByRole("button", { name: "Zapisz regułę" }));

    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect(api.addDefinition).toHaveBeenCalledWith(
      "wybicie",
      "Wybicie",
      "",
      expect.objectContaining({ resolution: "HOUR", setups: expect.any(Array) }),
      expect.anything(),
    );
  });

  it("keeps the module's refusal beside the rule it is about", async () => {
    const api = fakeApi({
      addDefinition: vi
        .fn()
        .mockRejectedValue(
          new Error("fact 'ma' names indicator 'sorcery', which the archive does not announce"),
        ),
    });
    const saved = vi.fn();
    render(
      <DefinitionDialog client={api} source={fakeSource()} onClose={() => {}} onSaved={saved} />,
    );

    await userEvent.type(await screen.findByLabelText("Identyfikator"), "wybicie");
    await userEvent.type(screen.getByLabelText("Nazwa"), "Wybicie");
    await userEvent.click(screen.getByRole("button", { name: "Zapisz regułę" }));

    expect(await screen.findByText(/sorcery/)).toBeInTheDocument();
    // Still open, still holding what was composed: a refusal thrown at the screen
    // underneath would have lost the rule it explains.
    expect(screen.getByLabelText("Nazwa")).toHaveValue("Wybicie");
    expect(saved).not.toHaveBeenCalled();
  });

  it("leaves the catalogue where every other reader of it looks", async () => {
    // The query cache is shared and keyed by name alone. This dialog once read the catalogue under the chart's
    // key holding the whole document, and the screen that broke was the chart grid.
    const source = fakeSource();
    render(
      <DefinitionDialog
        client={fakeApi()}
        source={source}
        onClose={() => {}}
        onSaved={() => {}}
      />,
    );
    await screen.findByLabelText("Identyfikator");

    function AChartWouldRead() {
      const catalogue = useIndicatorCatalogue(source);
      return <span data-testid="ids">{catalogue.entries.map((one) => one.id).join(",")}</span>;
    }
    render(<AChartWouldRead />);

    await waitFor(() => expect(screen.getByTestId("ids")).toHaveTextContent("ema,atr"));
  });

  it("says that saving a revision moves no running watch", async () => {
    render(
      <DefinitionDialog
        client={fakeApi()}
        source={fakeSource()}
        onClose={() => {}}
        onSaved={() => {}}
      />,
    );

    expect(await screen.findByText(/niczego nie uruchamia/)).toBeInTheDocument();
  });
});
