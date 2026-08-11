/**
 * The picker on its own, driven by props — the catalogue is long enough that finding an
 * entry is its own problem, separate from what happens once one is chosen (`Chart.test.tsx`
 * covers that half).
 *
 * `market-data-indicators` spec, "Wyszukiwanie po nazwie potocznej"; `terminal-chart` spec,
 * "Operator wybiera wskaźniki z tego, co oferuje źródło".
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { IndicatorCatalogueEntry } from "../../data/types";
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

  it("finds an indicator by a colloquial name it is known under, not only by its id", async () => {
    const user = userEvent.setup();
    renderPicker();
    await open(user);

    await user.type(screen.getByLabelText("Filter indicators"), "fair value gap");

    expect(screen.getAllByRole("checkbox")).toHaveLength(1);
    expect(screen.getByRole("checkbox", { name: /^range_gap$/i })).toBeInTheDocument();
  });

  it("says which alias matched, so a row that does not contain the query still explains itself", async () => {
    const user = userEvent.setup();
    renderPicker();
    await open(user);

    await user.type(screen.getByLabelText("Filter indicators"), "fvg");

    // Without this the row reads `RANGE_GAP / Range Gap` and the operator is left to
    // guess why their search returned it.
    expect(screen.getByText("FVG")).toBeInTheDocument();
    expect(screen.queryByText("Range Gap")).not.toBeInTheDocument();
  });

  it("matches on the group, which is the search worth having with sixty entries", async () => {
    const user = userEvent.setup();
    renderPicker();
    await open(user);

    await user.type(screen.getByLabelText("Filter indicators"), "zones");

    expect(screen.getAllByRole("checkbox")).toHaveLength(2);
    expect(screen.getByRole("checkbox", { name: /^range_gap$/i })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /^session_range_london$/i })).toBeInTheDocument();
  });

  it("ignores case and surrounding whitespace", async () => {
    const user = userEvent.setup();
    renderPicker();
    await open(user);

    await user.type(screen.getByLabelText("Filter indicators"), "  MaCd  ");

    expect(screen.getAllByRole("checkbox")).toHaveLength(1);
    expect(screen.getByRole("checkbox", { name: /^macd$/i })).toBeInTheDocument();
  });

  it("distinguishes a catalogue that offers nothing from a filter that matched nothing", async () => {
    const user = userEvent.setup();
    renderPicker();
    await open(user);

    await user.type(screen.getByLabelText("Filter indicators"), "supertrend");

    expect(screen.getByText(/no indicator matches/i)).toHaveTextContent("supertrend");
    expect(screen.queryByText("No indicators available.")).not.toBeInTheDocument();
    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
  });

  it("still says so when the catalogue itself is empty", async () => {
    const user = userEvent.setup();
    renderPicker({ entries: [] });
    await open(user);

    expect(screen.getByText("No indicators available.")).toBeInTheDocument();
    expect(screen.queryByText(/no indicator matches/i)).not.toBeInTheDocument();
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

  it("hides without deselecting — filtering is a view of the catalogue, not a decision", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <IndicatorPicker
        entries={CATALOGUE}
        selections={[{ id: "ema", params: {} }]}
        onChange={onChange}
        canDraw={() => true}
      />,
    );
    await open(user);

    await user.type(screen.getByLabelText("Filter indicators"), "rsi");

    expect(screen.queryByRole("checkbox", { name: /^ema$/i })).not.toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /indicators/i })).toHaveTextContent("Indicators (1)");
  });
});
