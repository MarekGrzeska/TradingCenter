import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MarketDataError } from "../data/types";
import { PolymarketView } from "./PolymarketView";
import type {
  EventChanges,
  Group,
  PolymarketApi,
  SnapshotEntry,
  TrackedEvent,
} from "./polymarketApi";

/**
 * The tab, from the operator's seat. What is asserted here is what the screen *claims* —
 * that a market is not a coin, that a price carries its age, that an uncovered window says
 * so instead of showing a zero, and that a refusal reads differently from an outage.
 */

function outcome(id: number, name: string, price: number | null = 0.5) {
  return {
    id,
    name,
    price,
    priceAt: price === null ? null : new Date(),
    lastTrade: null,
    collectedFrom: new Date("2026-05-24T00:00:00Z"),
  };
}

function event(overrides: Partial<TrackedEvent> = {}): TrackedEvent {
  return {
    id: 1,
    providerEventId: "0xabc",
    slug: "fed-cuts-in-march",
    title: "Fed cuts in March",
    url: "https://polymarket.com/event/fed-cuts-in-march",
    group: null,
    trackedAt: new Date(),
    collection: { state: "collecting", lastSampleAt: new Date(), reason: null },
    markets: [
      {
        id: 4,
        question: "Will the Fed cut in March?",
        label: null,
        negRisk: false,
        resolvedOutcome: null,
        outcomes: [outcome(7, "Yes", 0.62), outcome(8, "No", 0.38)],
      },
    ],
    ...overrides,
  };
}

function fakeApi(overrides: Partial<PolymarketApi> = {}): PolymarketApi {
  const base: PolymarketApi = {
    listEvents: async () => [event()],
    readEvent: async () => event(),
    snapshot: async () => [],
    changes: async () => ({ eventId: 1, outcomes: [] }) as EventChanges,
    history: async () => ({ outcomeId: 7, points: [], collectedFrom: null, collectedTo: null }),
    trackEvent: async () => ({ event: event(), alreadyTracked: false }),
    endTracking: async () => event(),
    deleteHistory: async () => ({ samplesDeleted: 0, rangesDeleted: 0 }),
    listGroups: async () => [] as Group[],
    createGroup: async () => ({ id: 1, name: "macro", eventCount: 0 }),
    deleteGroup: async () => {},
    assignGroup: async () => {},
  };
  return { ...base, ...overrides };
}

describe("PolymarketView", () => {
  it("names an empty list as empty and says what fills it", async () => {
    render(<PolymarketView api={fakeApi({ listEvents: async () => [] })} />);

    expect(await screen.findByText(/nothing is being tracked/i)).toBeInTheDocument();
    expect(screen.getByText(/bring an event under observation/i)).toBeInTheDocument();
  });

  it("shows every outcome of a multi-outcome market, not just the highest", async () => {
    const nominee = event({
      markets: [
        {
          id: 9,
          question: "Who wins the nomination?",
          label: "Democratic nominee",
          negRisk: true,
          resolvedOutcome: null,
          outcomes: [
            outcome(11, "Newsom", 0.31),
            outcome(12, "Harris", 0.19),
            outcome(13, "Someone else", 0.5),
          ],
        },
      ],
    });

    render(<PolymarketView api={fakeApi({ listEvents: async () => [nominee] })} />);

    expect(await screen.findByText("Newsom")).toBeInTheDocument();
    expect(screen.getByText("Harris")).toBeInTheDocument();
    expect(screen.getByText("Someone else")).toBeInTheDocument();
    // The set is mutually exclusive and its prices need not sum to 100%; saying so is
    // cheaper than an operator working out why they do not.
    expect(screen.getByText(/exclusive set/i)).toBeInTheDocument();
  });

  it("reads every price in one request rather than one per outcome", async () => {
    const calls = vi.fn(async (): Promise<SnapshotEntry[]> => []);

    render(<PolymarketView api={fakeApi({ snapshot: calls })} />);

    await screen.findByText("Fed cuts in March");
    await waitFor(() => expect(calls).toHaveBeenCalledTimes(1));
  });

  it("prefers the snapshot's price over the one the list was fetched with", async () => {
    const fresh: SnapshotEntry[] = [
      {
        eventId: 1,
        eventSlug: "fed-cuts-in-march",
        marketId: 4,
        marketLabel: null,
        outcomeId: 7,
        outcomeName: "Yes",
        price: 0.71,
        priceAt: new Date(),
      },
    ];

    render(<PolymarketView api={fakeApi({ snapshot: async () => fresh })} />);

    expect(await screen.findByText("71.0%")).toBeInTheDocument();
    expect(screen.queryByText("62.0%")).not.toBeInTheDocument();
  });

  it("says a price has aged rather than showing it as the price now", async () => {
    const old = event({
      markets: [
        {
          id: 4,
          question: "Will the Fed cut in March?",
          label: null,
          negRisk: false,
          resolvedOutcome: null,
          outcomes: [
            {
              ...outcome(7, "Yes", 0.62),
              priceAt: new Date(Date.now() - 40 * 60_000),
            },
          ],
        },
      ],
    });

    render(<PolymarketView api={fakeApi({ listEvents: async () => [old] })} />);

    expect(await screen.findByText("40 min ago")).toBeInTheDocument();
  });

  it("says an outcome with nothing collected is not collected, not zero", async () => {
    const blank = event({
      markets: [
        {
          id: 4,
          question: "Will the Fed cut in March?",
          label: null,
          negRisk: false,
          resolvedOutcome: null,
          outcomes: [outcome(7, "Yes", null)],
        },
      ],
    });

    render(<PolymarketView api={fakeApi({ listEvents: async () => [blank] })} />);

    expect(await screen.findByText(/not collected yet/i)).toBeInTheDocument();
    expect(screen.queryByText("0.0%")).not.toBeInTheDocument();
  });

  it("shows an uncovered window as a named absence rather than as no movement", async () => {
    const changes: EventChanges = {
      eventId: 1,
      outcomes: [
        {
          outcomeId: 7,
          name: "Yes",
          price: 0.62,
          windows: [
            {
              window: "24h",
              change: 0.021,
              unavailable: null,
              baselineAt: new Date("2026-08-21T09:58:00Z"),
            },
            {
              window: "7d",
              change: null,
              unavailable: "collected history reaches back 2 days",
              baselineAt: null,
            },
          ],
        },
      ],
    };

    render(<PolymarketView api={fakeApi({ changes: async () => changes })} />);

    await userEvent.click(await screen.findByRole("button", { name: /Fed cuts in March/ }));

    expect(await screen.findByText("+2.1 pp")).toBeInTheDocument();
    const uncovered = await screen.findByText(/no coverage/i);
    expect(uncovered).toHaveAttribute("title", "collected history reaches back 2 days");
    // A zero here would be a claim about the market where the truth is about the archive.
    expect(screen.queryByText("0.0 pp")).not.toBeInTheDocument();
  });

  it("does not ask for the windows until an event is opened", async () => {
    const changes = vi.fn(async () => ({ eventId: 1, outcomes: [] }) as EventChanges);

    render(<PolymarketView api={fakeApi({ changes })} />);

    await screen.findByText("Fed cuts in March");
    expect(changes).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: /Fed cuts in March/ }));
    await waitFor(() => expect(changes).toHaveBeenCalledTimes(1));
  });

  it("tells a refusal apart from a module that did not answer", async () => {
    const refused = fakeApi({
      listEvents: async () => {
        throw new MarketDataError("refused", "caller may not reach the REST contract");
      },
    });
    const { unmount } = render(<PolymarketView api={refused} />);

    expect(
      await screen.findByText(/caller may not reach the REST contract/i),
    ).toBeInTheDocument();
    unmount();

    const down = fakeApi({
      listEvents: async () => {
        throw new MarketDataError("unreachable", "polymarket-data is not reachable");
      },
    });
    render(<PolymarketView api={down} />);

    expect(await screen.findByText(/is not reachable/i)).toBeInTheDocument();
  });

  it("narrows the list to one group and asks the module for it", async () => {
    const listEvents = vi.fn(async () => [event()]);
    render(
      <PolymarketView
        api={fakeApi({
          listEvents,
          listGroups: async () => [{ id: 3, name: "macro", eventCount: 1 }],
        })}
      />,
    );

    await userEvent.click(await screen.findByRole("button", { name: /macro/ }));

    await waitFor(() =>
      expect(listEvents).toHaveBeenLastCalledWith(expect.anything(), { groupId: 3 }),
    );
  });

  it("says the scale it is showing, because 0.62 read as 62 is wrong by two orders", async () => {
    render(<PolymarketView api={fakeApi()} />);

    expect(await screen.findByText(/0–1 scale/i)).toBeInTheDocument();
  });
});

describe("the group filter", () => {
  it("is absent when there are no groups, rather than an empty row of buttons", async () => {
    render(<PolymarketView api={fakeApi()} />);

    await screen.findByText("Fed cuts in March");
    expect(screen.queryByText("Groups")).not.toBeInTheDocument();
  });

  it("keeps the whole list reachable beside the groups", async () => {
    render(
      <PolymarketView
        api={fakeApi({ listGroups: async () => [{ id: 3, name: "macro", eventCount: 1 }] })}
      />,
    );

    const nav = await screen.findByRole("navigation");
    expect(within(nav).getByRole("button", { name: "all" })).toBeInTheDocument();
  });
});
