/**
 * The picker on its own, driven by props — the catalogue is long enough that finding an
 * entry is its own problem, separate from what happens once one is chosen (`Chart.test.tsx`
 * covers that half).
 *
 * `market-data-indicators` spec, "Wyszukiwanie po nazwie potocznej"; `terminal-chart` spec,
 * "Operator wybiera wskaźniki z tego, co oferuje źródło".
 */

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import type { IndicatorCatalogueEntry, IndicatorSelection } from "../../data/types";
import { IndicatorPicker } from "./IndicatorPicker";

function entry(over: Partial<IndicatorCatalogueEntry> = {}): IndicatorCatalogueEntry {
  return {
    id: "ema",
    name: "Exponential Moving Average",
    aliases: [],
    group: "averages",
    output: "lines",
    params: [],
    lines: [{ key: "ema", label: "EMA {period}", style: null }],
    render: {
      pane: "price",
      style: "line",
      scale: "price",
      autoscale: true,
      range: null,
      levels: [],
    },
    warmupKind: "decay",
    ...over,
  };
}

const CATALOGUE = [
  entry(),
  entry({ id: "rsi", name: "Relative Strength Index", group: "oscillators" }),
  entry({ id: "macd", name: "MACD", group: "oscillators" }),
  entry({
    id: "range_gap",
    name: "Range Gap",
    group: "zones",
    aliases: ["FVG", "Fair Value Gap"],
    output: "zones",
  }),
  entry({ id: "session_range_london", name: "London Session Range", group: "zones", output: "zones" }),
];

function renderPicker(over: { entries?: IndicatorCatalogueEntry[] } = {}) {
  const onChange = vi.fn();
  render(
    <IndicatorPicker
      entries={over.entries ?? CATALOGUE}
      selections={[]}
      onChange={onChange}
      canDraw={() => true}
    />,
  );
  return { onChange };
}

async function open(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: /indicators/i }));
}

const EMA_WITH_PERIOD = entry({
  params: [{ name: "period", type: "int", default: 20, min: 2, max: 5000 }],
});

/** The picker driven by its own output, the way `Chart.tsx` drives it — adding a second
 *  instance is only observable if the selections it produced come back to it. */
function LivePicker({ entries }: { entries: IndicatorCatalogueEntry[] }) {
  const [selections, setSelections] = useState<IndicatorSelection[]>([]);
  return (
    <>
      <IndicatorPicker
        entries={entries}
        selections={selections}
        onChange={setSelections}
        canDraw={() => true}
      />
      <pre data-testid="selections">{JSON.stringify(selections.map(({ key: _k, ...rest }) => rest))}</pre>
    </>
  );
}

function selectionsShown(): Array<Omit<IndicatorSelection, "key">> {
  return JSON.parse(screen.getByTestId("selections").textContent ?? "[]");
}

async function addInstances(user: ReturnType<typeof userEvent.setup>, count: number) {
  render(<LivePicker entries={[EMA_WITH_PERIOD]} />);
  await open(user);
  await user.click(screen.getByRole("checkbox", { name: /^ema$/i }));
  for (let i = 1; i < count; i += 1) {
    await user.click(screen.getByRole("button", { name: /add another ema/i }));
  }
}

async function setPeriod(
  user: ReturnType<typeof userEvent.setup>,
  group: HTMLElement,
  value: string,
) {
  const input = within(group).getByLabelText("period");
  await user.clear(input);
  await user.type(input, value);
  await user.tab();
}

describe("IndicatorPicker — several instances of one catalogue entry", () => {
  it("draws the same average three times, each with its own period", async () => {
    const user = userEvent.setup();
    await addInstances(user, 3);

    await setPeriod(user, screen.getByRole("group", { name: "EMA 1" }), "20");
    await setPeriod(user, screen.getByRole("group", { name: "EMA 2" }), "50");
    await setPeriod(user, screen.getByRole("group", { name: "EMA 3" }), "200");

    expect(selectionsShown()).toEqual([
      { id: "ema", params: { period: 20 }, color: null },
      { id: "ema", params: { period: 50 }, color: null },
      { id: "ema", params: { period: 200 }, color: null },
    ]);
  });

  it("adds a second instance carrying the catalogue's defaults, without refusing the duplicate", async () => {
    const user = userEvent.setup();
    await addInstances(user, 2);

    // Both sit at period 20 the moment the second is added. Refusing that, or guessing a
    // different period for the operator, is what the instance key exists to avoid.
    expect(selectionsShown()).toEqual([
      { id: "ema", params: { period: 20 }, color: null },
      { id: "ema", params: { period: 20 }, color: null },
    ]);
  });

  it("changes the period of one instance and leaves the others where they were", async () => {
    const user = userEvent.setup();
    await addInstances(user, 3);
    await setPeriod(user, screen.getByRole("group", { name: "EMA 2" }), "50");

    expect(selectionsShown()).toEqual([
      { id: "ema", params: { period: 20 }, color: null },
      { id: "ema", params: { period: 50 }, color: null },
      { id: "ema", params: { period: 20 }, color: null },
    ]);
  });

  it("removes one instance and keeps the rest", async () => {
    const user = userEvent.setup();
    await addInstances(user, 3);
    await setPeriod(user, screen.getByRole("group", { name: "EMA 2" }), "50");

    await user.click(screen.getByRole("button", { name: "Remove EMA 2" }));

    expect(selectionsShown()).toEqual([
      { id: "ema", params: { period: 20 }, color: null },
      { id: "ema", params: { period: 20 }, color: null },
    ]);
    expect(screen.queryByRole("group", { name: "EMA 3" })).not.toBeInTheDocument();
  });

  it("counts instances, not catalogue entries", async () => {
    const user = userEvent.setup();
    await addInstances(user, 3);

    expect(screen.getByRole("button", { name: /indicators/i })).toHaveTextContent("Indicators (3)");
  });

  it("unchecking the entry removes every instance of it", async () => {
    const user = userEvent.setup();
    await addInstances(user, 3);

    await user.click(screen.getByRole("checkbox", { name: /^ema$/i }));

    expect(selectionsShown()).toEqual([]);
  });

  it("keeps a param out of range from reaching the selection, and says which range", async () => {
    const user = userEvent.setup();
    await addInstances(user, 1);

    await setPeriod(user, screen.getByRole("group", { name: "EMA" }), "1");

    expect(screen.getByText(/period must be between 2 and 5000/i)).toBeInTheDocument();
    expect(selectionsShown()).toEqual([{ id: "ema", params: { period: 20 }, color: null }]);
  });
});

describe("IndicatorPicker — colour per instance", () => {
  it("stores the chosen colour as a palette token on that instance alone", async () => {
    const user = userEvent.setup();
    await addInstances(user, 2);

    await user.click(
      within(screen.getByRole("group", { name: "EMA 2" })).getByRole("button", { name: "Colour 5" }),
    );

    expect(selectionsShown()).toEqual([
      { id: "ema", params: { period: 20 }, color: null },
      { id: "ema", params: { period: 20 }, color: "--color-indicator-5" },
    ]);
  });

  it("marks the chosen swatch and clears it again on Auto", async () => {
    const user = userEvent.setup();
    await addInstances(user, 1);
    const group = () => screen.getByRole("group", { name: "EMA" });

    await user.click(within(group()).getByRole("button", { name: "Colour 1" }));
    expect(within(group()).getByRole("button", { name: "Colour 1" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    await user.click(within(group()).getByRole("button", { name: "Auto" }));

    expect(selectionsShown()).toEqual([{ id: "ema", params: { period: 20 }, color: null }]);
    expect(within(group()).getByRole("button", { name: "Colour 1" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("offers the whole validated palette, named so it can be picked without a mouse", async () => {
    const user = userEvent.setup();
    await addInstances(user, 1);

    const swatches = within(screen.getByRole("group", { name: "EMA" })).getAllByRole("button", {
      name: /^Colour \d$/,
    });
    expect(swatches).toHaveLength(8);
  });
});

describe("IndicatorPicker — filtering a long catalogue", () => {
  it("narrows the list to what the operator typed, and brings it all back when cleared", async () => {
    const user = userEvent.setup();
    renderPicker();
    await open(user);

    expect(screen.getAllByRole("checkbox")).toHaveLength(5);

    await user.type(screen.getByLabelText("Filter indicators"), "rsi");

    expect(screen.getAllByRole("checkbox")).toHaveLength(1);
    expect(screen.getByRole("checkbox", { name: /^rsi$/i })).toBeInTheDocument();

    await user.clear(screen.getByLabelText("Filter indicators"));

    expect(screen.getAllByRole("checkbox")).toHaveLength(5);
  });

  it("starts from the whole catalogue again when reopened", async () => {
    const user = userEvent.setup();
    renderPicker();
    await open(user);
    await user.type(screen.getByLabelText("Filter indicators"), "rsi");
    expect(screen.getAllByRole("checkbox")).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: /indicators/i }));
    await open(user);

    expect(screen.getAllByRole("checkbox")).toHaveLength(5);
    expect(screen.getByLabelText("Filter indicators")).toHaveValue("");
  });
});
