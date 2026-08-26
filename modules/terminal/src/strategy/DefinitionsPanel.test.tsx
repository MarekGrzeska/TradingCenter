import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DefinitionsPanel } from "./DefinitionsPanel";
import type { Definition, Strategy, StrategyApi, Watch } from "./strategyApi";

/**
 * The list of rules, and the one distinction it exists to make: which of them is code. A greyed-out edit button with
 * no explanation reads as a fault; "kod w obrazie" says it is a decision, and where the rule lives.
 */

const CODED: Strategy = {
  id: "baseline_ma_cross",
  name: "Baseline · moving-average cross",
  description: "the floor",
  resolution: "HOUR",
  candles: 300,
  facts: [],
  params: [],
  source: "code",
  revision: null,
};

const WRITTEN: Definition = {
  id: 7,
  strategyId: "wybicie_kanalu",
  name: "Wybicie kanału",
  description: "",
  latestVersion: 4,
  createdAt: new Date("2026-08-22T09:00:00Z"),
};

function pinnedWatch(revisionId: number | null): Watch {
  return {
    id: 1,
    strategyId: "wybicie_kanalu",
    symbol: "US100",
    parameterSetId: 3,
    active: true,
    createdAt: new Date("2026-08-22T09:00:00Z"),
    strategyRevisionId: revisionId,
  };
}

function fakeApi(overrides: Partial<StrategyApi> = {}): StrategyApi {
  return {
    listDefinitions: vi.fn().mockResolvedValue([WRITTEN]),
    listRevisions: vi.fn().mockResolvedValue([]),
    ...overrides,
  } as unknown as StrategyApi;
}

describe("the list of rules", () => {
  it("shows each written rule with its newest revision", async () => {
    render(
      <DefinitionsPanel
        client={fakeApi()}
        strategies={[]}
        watches={[]}
        onChanged={() => {}}
      />,
    );

    expect(await screen.findByText("Wybicie kanału")).toBeInTheDocument();
    expect(screen.getByText("rewizja 4")).toBeInTheDocument();
  });

  it("names a coded entry as code and offers no way to edit it", async () => {
    render(
      <DefinitionsPanel
        client={fakeApi()}
        strategies={[CODED]}
        watches={[]}
        onChanged={() => {}}
      />,
    );

    const coded = await screen.findByTestId("coded-entry");
    expect(coded).toHaveTextContent("kod w obrazie");
    expect(coded).not.toHaveTextContent("Nowa rewizja");
  });

  it("says a pinned watch keeps computing its own revision", async () => {
    render(
      <DefinitionsPanel
        client={fakeApi()}
        strategies={[]}
        watches={[pinnedWatch(11)]}
        onChanged={() => {}}
      />,
    );

    expect(await screen.findByText(/przypiętą rewizję/)).toBeInTheDocument();
  });

  it("says so when the rules could not be read", async () => {
    const api = fakeApi({
      listDefinitions: vi.fn().mockRejectedValue(new Error("moduł nie odpowiedział")),
    });

    render(
      <DefinitionsPanel client={api} strategies={[]} watches={[]} onChanged={() => {}} />,
    );

    expect(await screen.findByText(/moduł nie odpowiedział/)).toBeInTheDocument();
  });
});
