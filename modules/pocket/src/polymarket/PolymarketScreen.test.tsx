import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
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
    renameGroup: vi.fn(async (id: number, name: string) => ({ id, name, eventCount: 0 })),
    deleteGroup: vi.fn(async () => {}),
    assignGroup: vi.fn(async () => {}),
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
    // A polled screen on a phone has to say when it last managed to poll: a background tab is
    // throttled by every mobile browser and suspended outright by Safari.
    expect(screen.getByRole("button", { name: /updated/i })).toBeInTheDocument();

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

describe("tidying groups", () => {
  const GROUPS = [
    { id: 3, name: "Crypto", eventCount: 2 },
    { id: 4, name: "crypto currency", eventCount: 1 },
  ];

  it("moves an event into another group", async () => {
    const api = anApi({ listGroups: vi.fn(async () => GROUPS) });

    render(<PolymarketScreen api={api} />);
    await userEvent.click(await screen.findByRole("button", { name: /will it happen/i }));
    await userEvent.click(screen.getByRole("button", { name: "Move to group" }));
    await userEvent.selectOptions(screen.getByLabelText("Group"), "Crypto");
    await userEvent.click(screen.getByRole("button", { name: "Move" }));

    expect(api.assignGroup).toHaveBeenCalledWith(100, 3, expect.anything());
    expect(await screen.findByRole("status")).toHaveTextContent("is in “Crypto” now");
  });

  it("merges a duplicate by deleting it into the group that stays", async () => {
    const api = anApi({ listGroups: vi.fn(async () => GROUPS) });

    render(<PolymarketScreen api={api} />);
    await userEvent.click(await screen.findByRole("button", { name: "Groups" }));
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: /crypto currency/ }),
    );
    await userEvent.selectOptions(screen.getByLabelText("Move its events to"), "Crypto");
    await userEvent.click(screen.getByRole("button", { name: "Delete group" }));

    expect(api.deleteGroup).toHaveBeenCalledWith(4, expect.anything(), 3);
  });

  it("keeps the sheet open with the archive's reason when a rename is refused", async () => {
    const api = anApi({
      listGroups: vi.fn(async () => GROUPS),
      renameGroup: vi.fn(async () => {
        throw new ArchiveError("refused", "a group named 'Crypto' already exists");
      }),
    });

    render(<PolymarketScreen api={api} />);
    await userEvent.click(await screen.findByRole("button", { name: "Groups" }));
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: /crypto currency/ }),
    );
    const field = screen.getByLabelText("Name");
    await userEvent.clear(field);
    await userEvent.type(field, "crypto");
    await userEvent.click(screen.getByRole("button", { name: "Rename" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("already exists");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
