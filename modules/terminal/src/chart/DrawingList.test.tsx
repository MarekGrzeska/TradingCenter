import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AgentChartDrawing } from "../agent/agentApi";
import type { ChartDrawings } from "./Chart";
import { DrawingList } from "./DrawingList";

function drawing(
  id: number,
  geometry: AgentChartDrawing["geometry"],
  label: string | null = null,
  hidden = false,
): AgentChartDrawing {
  return {
    id,
    symbol: "US100",
    geometry,
    label,
    color: null,
    hidden,
    createdAt: 1767398400,
    updatedAt: 1767398400,
  };
}

const A_LEVEL = drawing(1, { kind: "level", price: 21500, at: null }, "weekly high");

function props(overrides: Partial<ChartDrawings> = {}): ChartDrawings {
  return {
    items: [A_LEVEL],
    status: "ready",
    error: null,
    remove: vi.fn(async () => null),
    patch: vi.fn(async () => null),
    ...overrides,
  };
}

/** The list does not own the selection any more — `Chart` does, and hands it back down
 *  (`terminal-chart-objects` spec, "Wskazanie jest jedno, wspólne z listą"). This stands
 *  in for that owner so the list can be exercised on its own. */
function Host({
  drawings,
  initialSelectedId = null,
  onSelect,
}: {
  drawings: ChartDrawings;
  initialSelectedId?: number | null;
  onSelect?: (id: number | null) => void;
}) {
  const [selectedId, setSelectedId] = useState<number | null>(initialSelectedId);
  return (
    <DrawingList
      drawings={drawings}
      selectedId={selectedId}
      onSelect={(id) => {
        setSelectedId(id);
        onSelect?.(id);
      }}
    />
  );
}

async function open(drawings: ChartDrawings, initialSelectedId: number | null = null) {
  render(<Host drawings={drawings} initialSelectedId={initialSelectedId} />);
  await userEvent.click(screen.getByLabelText("Drawn objects"));
}

describe("DrawingList", () => {
  it("shows each object's shape, prices, caption and when it was drawn", async () => {
    await open(props());

    const row = screen.getByTestId("drawing-1");
    expect(row).toHaveTextContent("level");
    expect(row).toHaveTextContent("21500");
    expect(row).toHaveTextContent("weekly high");
    expect(row).toHaveTextContent(/drawn/);
  });

  it("shows a zone's two prices and a trend line's two", async () => {
    await open(
      props({
        items: [
          drawing(2, { kind: "zone", top: 21600, bottom: 21550, from: null, to: null }),
          drawing(3, {
            kind: "trendline",
            a: { time: 100, price: 21000 },
            b: { time: 200, price: 21400 },
          }),
        ],
      }),
    );

    expect(screen.getByTestId("drawing-2")).toHaveTextContent("21600 – 21550");
    expect(screen.getByTestId("drawing-3")).toHaveTextContent("21000 – 21400");
  });

  it("removes one object", async () => {
    const remove = vi.fn(async () => null);
    await open(props({ remove }));

    await userEvent.click(screen.getByLabelText("Remove drawing 1"));
    expect(remove).toHaveBeenCalledWith(1);
  });

  it("says a removal failed and leaves the row where it was", async () => {
    // `terminal-chart` spec, "Usunięcie się nie powiodło": the object stays on the list
    // and on the chart, because it stayed in the record.
    const remove = vi.fn(async () => "no drawing #1");
    await open(props({ remove }));

    await userEvent.click(screen.getByLabelText("Remove drawing 1"));

    expect(await screen.findByText("no drawing #1")).toBeInTheDocument();
    expect(screen.getByTestId("drawing-1")).toBeInTheDocument();
  });

  it("corrects a price, sending only what moved", async () => {
    const patch = vi.fn(async () => null);
    await open(props({ patch }));

    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    const field = screen.getByLabelText("Price of drawing 1");
    await userEvent.clear(field);
    await userEvent.type(field, "21550");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(patch).toHaveBeenCalledWith(1, { price: 21550 });
  });

  it("corrects a caption without touching the price", async () => {
    const patch = vi.fn(async () => null);
    await open(props({ patch }));

    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    const caption = screen.getByLabelText("Caption of drawing 1");
    await userEvent.clear(caption);
    await userEvent.type(caption, "moved up");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(patch).toHaveBeenCalledWith(1, { label: "moved up" });
  });

  it("offers only the price roles this shape has", async () => {
    await open(props({ items: [drawing(2, { kind: "zone", top: 21600, bottom: 21550, from: null, to: null })] }));
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));

    expect(screen.getByLabelText("Top of drawing 2")).toBeInTheDocument();
    expect(screen.getByLabelText("Bottom of drawing 2")).toBeInTheDocument();
    // A level's `price` is not a field a zone has — offering it would be a form that can
    // only be refused by the module.
    expect(screen.queryByLabelText("Price of drawing 2")).toBeNull();
  });

  it("refuses a price that is not one before asking the module", async () => {
    const patch = vi.fn(async () => null);
    await open(props({ patch }));

    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    const field = screen.getByLabelText("Price of drawing 1");
    await userEvent.clear(field);
    await userEvent.type(field, "0");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(patch).not.toHaveBeenCalled();
    expect(screen.getByText(/above zero/)).toBeInTheDocument();
  });

  it("says a correction failed and keeps the form open", async () => {
    const patch = vi.fn(async () => "a zone's top must stay above its bottom");
    await open(props({ patch }));

    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    const field = screen.getByLabelText("Price of drawing 1");
    await userEvent.clear(field);
    await userEvent.type(field, "21550");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText(/must stay above/)).toBeInTheDocument();
    expect(screen.getByLabelText("Price of drawing 1")).toBeInTheDocument();
  });

  it("an instrument with nothing on it says so", async () => {
    // Not an absent list: `terminal-chart` spec, "Instrument bez obiektów" — the empty
    // case must be tellable apart from a read that failed.
    await open(props({ items: [] }));

    expect(screen.getByText("Nothing is drawn on this instrument.")).toBeInTheDocument();
  });

  it("a failed read says so, and does not read as an empty instrument", async () => {
    await open(props({ items: [], status: "error", error: "agent is not reachable" }));

    expect(screen.getByText(/could not be read/)).toBeInTheDocument();
    expect(screen.queryByText("Nothing is drawn on this instrument.")).toBeNull();
  });

  it("a failed read keeps showing what was already there", async () => {
    await open(props({ status: "error", error: "agent is not reachable" }));

    expect(screen.getByTestId("drawing-1")).toBeInTheDocument();
    expect(screen.getByText(/could not be read/)).toBeInTheDocument();
  });
});

describe("DrawingList — one selection, shared with the chart", () => {
  it("marks out the row of the object picked elsewhere", async () => {
    // Picked on the chart, arriving here as a prop: from the list's side there is no
    // difference between that and its own row being clicked, which is the point.
    await open(props(), 1);

    expect(screen.getByTestId("drawing-1")).toHaveAttribute("aria-current", "true");
  });

  it("reports a row picked here rather than keeping it", async () => {
    const onSelect = vi.fn();
    render(<Host drawings={props()} onSelect={onSelect} />);
    await userEvent.click(screen.getByLabelText("Drawn objects"));

    await userEvent.click(screen.getByRole("button", { name: "Edit" }));

    expect(onSelect).toHaveBeenCalledWith(1);
  });

  it("nothing is marked out when nothing is picked", async () => {
    await open(props(), null);

    expect(screen.getByTestId("drawing-1")).toHaveAttribute("aria-current", "false");
  });
});

describe("DrawingList — hiding without removing", () => {
  const HIDDEN = { ...A_LEVEL, hidden: true };

  it("hides a row's object through patch, not through remove", async () => {
    const patch = vi.fn(async () => null);
    const remove = vi.fn(async () => null);
    await open(props({ patch, remove }));

    await userEvent.click(screen.getByLabelText("Hide drawing 1"));

    expect(patch).toHaveBeenCalledWith(1, { hidden: true });
    expect(remove).not.toHaveBeenCalled();
  });

  it("keeps a hidden object on the list, marked out and offering to bring it back", async () => {
    // The list is the only way back to a hidden object, so one that dropped off it would
    // be hidden for good (`terminal-chart` spec, "Operator zarządza naniesionymi obiektami
    // z listy").
    const patch = vi.fn(async () => null);
    await open(props({ items: [HIDDEN], patch }));

    const row = screen.getByTestId("drawing-1");
    expect(row).toHaveAttribute("data-hidden", "true");
    expect(row).toHaveTextContent(/hidden/i);

    await userEvent.click(screen.getByLabelText("Show drawing 1"));
    expect(patch).toHaveBeenCalledWith(1, { hidden: false });
  });

  it("an instrument with everything hidden does not read as an empty one", async () => {
    // `terminal-chart` spec, "Instrument z samymi zgaszonymi obiektami".
    await open(props({ items: [HIDDEN] }));

    expect(screen.queryByText("Nothing is drawn on this instrument.")).toBeNull();
    expect(screen.getByTestId("drawing-1")).toBeInTheDocument();
  });

  it("says a failed hiding failed and leaves the row lit", async () => {
    const patch = vi.fn(async () => "the agent module is not reachable");
    await open(props({ patch }));

    await userEvent.click(screen.getByLabelText("Hide drawing 1"));

    expect(await screen.findByText("the agent module is not reachable")).toBeInTheDocument();
    expect(screen.getByTestId("drawing-1")).toHaveAttribute("data-hidden", "false");
  });
});
