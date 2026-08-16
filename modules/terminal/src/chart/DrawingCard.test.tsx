import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AgentChartDrawing } from "../agent/agentApi";
import type { ChartDrawings } from "./Chart";
import { cardPosition } from "./cardPosition";
import { DrawingCard } from "./DrawingCard";

function drawing(
  id: number,
  geometry: AgentChartDrawing["geometry"],
  label: string | null = "weekly high",
): AgentChartDrawing {
  return {
    id,
    symbol: "US100",
    geometry,
    label,
    color: null,
    createdAt: 1767398400,
    updatedAt: 1767398400,
  };
}

const A_LEVEL = drawing(1, { kind: "level", price: 21500, at: null });

function drawings(overrides: Partial<ChartDrawings> = {}): ChartDrawings {
  return {
    items: [A_LEVEL],
    status: "ready",
    error: null,
    remove: vi.fn(async () => null),
    patch: vi.fn(async () => null),
    ...overrides,
  };
}

function show(drawn: AgentChartDrawing, chartDrawings: ChartDrawings = drawings()) {
  const onClose = vi.fn();
  render(
    <DrawingCard drawing={drawn} drawings={chartDrawings} at={{ x: 100, y: 100 }} onClose={onClose} />,
  );
  return { onClose };
}

describe("DrawingCard — what the picked object is", () => {
  it("describes a level: its shape, its price, its caption and when it was drawn", async () => {
    show(A_LEVEL);

    const card = screen.getByTestId("drawing-card-1");
    expect(card).toHaveTextContent("level");
    expect(card).toHaveTextContent("21500");
    expect(card).toHaveTextContent("weekly high");
    expect(card).toHaveTextContent(/drawn/);
  });

  it("describes a zone by both its prices", () => {
    show(drawing(2, { kind: "zone", top: 21600, bottom: 21550, from: null, to: null }));

    const card = screen.getByTestId("drawing-card-2");
    expect(card).toHaveTextContent("zone");
    expect(card).toHaveTextContent("21600 – 21550");
  });

  it("describes a trend line by both its ends", () => {
    show(
      drawing(3, {
        kind: "trendline",
        a: { time: 100, price: 21000 },
        b: { time: 200, price: 21400 },
      }),
    );

    const card = screen.getByTestId("drawing-card-3");
    expect(card).toHaveTextContent("trend line");
    expect(card).toHaveTextContent("21000 – 21400");
  });
});

describe("DrawingCard — correcting and removing from the card", () => {
  it("corrects a price the same way the list does, sending only what moved", async () => {
    const patch = vi.fn(async () => null);
    show(A_LEVEL, drawings({ patch }));

    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    const field = screen.getByLabelText("Price of drawing 1");
    await userEvent.clear(field);
    await userEvent.type(field, "21550");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(patch).toHaveBeenCalledWith(1, { price: 21550 });
  });

  it("removes the object through the same call the list makes", async () => {
    const remove = vi.fn(async () => null);
    show(A_LEVEL, drawings({ remove }));

    await userEvent.click(screen.getByLabelText("Remove drawing 1"));

    expect(remove).toHaveBeenCalledWith(1);
  });

  it("says a correction failed and leaves the object as it was", async () => {
    // Same contract as the list's: the record did not change, so neither does the screen
    // (`terminal-chart-objects` spec, "Nieudane poprawienie z opisu").
    const patch = vi.fn(async () => "a level's price must stay above zero");
    show(A_LEVEL, drawings({ patch }));

    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    const field = screen.getByLabelText("Price of drawing 1");
    await userEvent.clear(field);
    await userEvent.type(field, "21550");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText(/must stay above zero/)).toBeInTheDocument();
    expect(screen.getByTestId("drawing-card-1")).toHaveTextContent("21500");
    expect(screen.getByLabelText("Price of drawing 1")).toBeInTheDocument();
  });

  it("says a removal failed and keeps the object described", async () => {
    const remove = vi.fn(async () => "no drawing #1");
    show(A_LEVEL, drawings({ remove }));

    await userEvent.click(screen.getByLabelText("Remove drawing 1"));

    expect(await screen.findByText("no drawing #1")).toBeInTheDocument();
    expect(screen.getByTestId("drawing-card-1")).toBeInTheDocument();
  });

  it("closes on the operator's own say-so", async () => {
    const { onClose } = show(A_LEVEL);

    await userEvent.click(screen.getByLabelText("Close object card"));

    expect(onClose).toHaveBeenCalled();
  });
});

describe("DrawingCard — where it stands", () => {
  const pane = { width: 800, height: 600 };

  it("opens on the side of the click that has room for it", () => {
    expect(cardPosition({ x: 100, y: 100 }, pane).left).toBeGreaterThan(100);
    // Near the right edge it goes the other way, rather than off the pane — and an object
    // near the right edge is the one most often looked at.
    expect(cardPosition({ x: 780, y: 100 }, pane).left).toBeLessThan(780);
    expect(cardPosition({ x: 100, y: 590 }, pane).top).toBeLessThan(590);
  });

  it("never leaves the pane, even in a corner too small for it either way", () => {
    const { left, top } = cardPosition({ x: 5, y: 5 }, { width: 100, height: 60 });
    expect(left).toBeGreaterThanOrEqual(0);
    expect(top).toBeGreaterThanOrEqual(0);
  });

  it("takes a corner of its own for an object chosen from the list", () => {
    // Nothing on the chart was clicked, so there is no pointer to sit beside.
    expect(cardPosition(null, pane)).toEqual({ left: 12, top: 12 });
  });
});
