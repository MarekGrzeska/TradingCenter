import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PolymarketScreen } from "./PolymarketScreen";
import type { PolymarketApi } from "./api";
import { ArchiveError } from "../data/http";
import { aMarket, anEvent, anOutcome } from "../test/builders";

function anApi(overrides: Partial<PolymarketApi> = {}): PolymarketApi {
  return {
    listEvents: vi.fn(async () => [anEvent()]),
    listGroups: vi.fn(async () => []),
    changes: vi.fn(async () => []),
    trackEvent: vi.fn(async () => ({ event: anEvent(), alreadyTracked: false })),
    removeEvent: vi.fn(async () => {}),
    ...overrides,
  };
}

describe("the observation screen", () => {
  it("shows what is tracked, and its markets once a card is opened", async () => {
    const api = anApi({
      listEvents: vi.fn(async () => [
        anEvent({
          title: "Rate cut in September",
          markets: [aMarket({ label: "50 bp", outcomes: [anOutcome({ price: 0.62 })] })],
        }),
      ]),
    });

    render(<PolymarketScreen api={api} />);

    expect(await screen.findByText("Rate cut in September")).toBeInTheDocument();
    expect(screen.getByText("62%")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { expanded: false }));

    expect(await screen.findByRole("link", { name: /polymarket\.com/i })).toBeInTheDocument();
    // The windows are asked for only once a card is open — one query per outcome is not what a
    // list of forty events should cost.
    expect(api.changes).toHaveBeenCalledWith("evt-100", expect.anything());
  });

  it("says the archive is down rather than showing an empty list", async () => {
    const api = anApi({
      listEvents: vi.fn(async () => {
        throw new ArchiveError("unreachable", "polymarket-data is not reachable");
      }),
    });

    render(<PolymarketScreen api={api} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("polymarket-data is not reachable");
    expect(screen.queryByText(/nothing is under observation/i)).not.toBeInTheDocument();
  });

  it("carries the archive's refusal into the sheet that asked for it", async () => {
    const api = anApi({
      trackEvent: vi.fn(async () => {
        throw new ArchiveError("refused", "already observing 40 events");
      }),
    });

    render(<PolymarketScreen api={api} />);
    await userEvent.click(screen.getByRole("button", { name: "Track event" }));
    await userEvent.type(
      screen.getByLabelText(/event address or slug/i),
      "https://polymarket.com/event/x",
    );
    await userEvent.click(screen.getByRole("button", { name: "Track" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("already observing 40 events");
    // Still open, and still holding what was typed: a refusal the operator can act on is not a
    // reason to make them start again.
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
