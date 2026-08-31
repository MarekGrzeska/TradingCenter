import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MarketDataError } from "../data/types";
import { PolymarketView } from "./PolymarketView";

// The real library draws to a canvas jsdom cannot render, reaching into a null 2d context inside a
// `requestAnimationFrame` that surfaces after the test that triggered it has finished.
vi.mock("./ProbabilityChart", () => ({
  ProbabilityChart: () => null,
}));

import type {
  EventChanges,
  Group,
  PolymarketApi,
  SnapshotEntry,
  TrackedEvent,
} from "./polymarketApi";

/**
 * The tab from the operator's seat: that a market is not a coin, that a price carries its age, that an uncovered
 * window says so instead of showing a zero, and that a refusal reads differently from an outage.
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

/** The card starts collapsed, so a test about an outcome row opens it first. That is the
 *  behaviour, not a workaround: an operator watching a dozen events sees a dozen lines. */
async function unfold(title = /Fed cuts in March/) {
  await userEvent.click(await screen.findByRole("button", { name: title }));
}

function fakeApi(overrides: Partial<PolymarketApi> = {}): PolymarketApi {
  const base: PolymarketApi = {
    listEvents: async () => [event()],
    readEvent: async () => event(),
    snapshot: async () => [],
    changes: async () => ({ eventId: 1, outcomes: [] }) as EventChanges,
    history: async () => ({ outcomeId: 7, points: [], collectedFrom: null, collectedTo: null }),
    trackEvent: async () => ({ event: event(), alreadyTracked: false }),
    removeEvent: async () => {},
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
    await unfold(/Who wins the nomination|Fed cuts in March/);

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
    await unfold();

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
    await unfold();

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
    await unfold();

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
    await unfold();

    expect(await screen.findByText("+2.1 pp")).toBeInTheDocument();
    const uncovered = await screen.findByText(/no coverage/i);
    expect(uncovered).toHaveAttribute("title", "collected history reaches back 2 days");
    // A zero here would be a claim about the market where the truth is about the archive.
    expect(screen.queryByText("0.0 pp")).not.toBeInTheDocument();
  });

  it("does not ask for the windows of an event nobody has opened", async () => {
    const changes = vi.fn(async () => ({ eventId: 1, outcomes: [] }) as EventChanges);

    render(<PolymarketView api={fakeApi({ changes })} />);

    // One request per event, so a folded list of a dozen would be a dozen requests for
    // numbers nobody has looked at.
    await screen.findByText("Fed cuts in March");
    expect(changes).not.toHaveBeenCalled();

    await unfold();
    await waitFor(() => expect(changes).toHaveBeenCalledTimes(1));
  });

  it("starts collapsed, carrying what identifies the observation and no price", async () => {
    render(<PolymarketView api={fakeApi()} />);

    // A summary quoting one outcome per market is a market reduced to a single "for" price, which the
    // unfolded view is forbidden to do. Folding is only the easiest place to slip past that rule.
    expect(await screen.findByText("Fed cuts in March")).toBeInTheDocument();
    expect(screen.getByText("collecting")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove" })).toBeInTheDocument();
    expect(screen.queryByText("62.0%")).not.toBeInTheDocument();
    expect(screen.queryAllByRole("meter")).toHaveLength(0);
  });

  it("shows the prices once the event is unfolded", async () => {
    render(<PolymarketView api={fakeApi()} />);

    await unfold();

    expect(await screen.findByText("62.0%")).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByRole("meter").length).toBeGreaterThan(0));
  });

  it("keeps an event unfolded across a refresh of the list", async () => {
    const listEvents = vi.fn(async () => [event()]);
    render(<PolymarketView api={fakeApi({ listEvents })} />);

    await unfold();
    await waitFor(() => expect(screen.getAllByRole("meter").length).toBeGreaterThan(1));

    await userEvent.click(screen.getByRole("button", { name: "Refresh now" }));
    await waitFor(() => expect(listEvents.mock.calls.length).toBeGreaterThan(1));

    // The prices move on their own every half minute; a fold that reset with them would
    // make the tab unusable for the one thing it is for — watching something.
    expect(screen.getAllByRole("meter").length).toBeGreaterThan(1);
  });

  it("folds resolved markets away, counts them, and can still show them", async () => {
    // A dated event resolves its markets one by one and each stays for good: ten of them is
    // a hundred rows saying nothing about now.
    const dated = event({
      markets: [
        {
          id: 1,
          question: "Cut in March?",
          label: "March",
          negRisk: false,
          resolvedOutcome: null,
          outcomes: [outcome(1, "Yes", 0.4), outcome(2, "No", 0.6)],
        },
        {
          id: 2,
          question: "Cut in August?",
          label: "August 6",
          negRisk: false,
          resolvedOutcome: "No",
          outcomes: [outcome(3, "Yes", 0), outcome(4, "No", 1)],
        },
      ],
    });

    render(<PolymarketView api={fakeApi({ listEvents: async () => [dated] })} />);
    await unfold();

    expect(await screen.findByText("March")).toBeInTheDocument();
    // Exact match: the picker still offers "August 6 · Yes", and it should — a resolved market's history is
    // the part the provider will not give back, so it stays reachable. What folds away is its row.
    expect(screen.queryByText("August 6")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "1 resolved market" }));
    expect(await screen.findByText("August 6")).toBeInTheDocument();
    expect(screen.getByText(/settled on No/)).toBeInTheDocument();
  });

  it("shows no window at all for a resolved market", async () => {
    const settled = event({
      markets: [
        {
          id: 2,
          question: "Cut in August?",
          label: "August 6",
          negRisk: false,
          resolvedOutcome: "No",
          outcomes: [outcome(3, "Yes", 0), outcome(4, "No", 1)],
        },
      ],
    });
    const changes: EventChanges = {
      eventId: 1,
      outcomes: [
        {
          outcomeId: 3,
          name: "Yes",
          price: 0,
          windows: [{ window: "5m", change: 0, unavailable: null, baselineAt: new Date() }],
        },
      ],
    };

    render(
      <PolymarketView api={fakeApi({ listEvents: async () => [settled], changes: async () => changes })} />,
    );
    await unfold();
    await userEvent.click(await screen.findByRole("button", { name: "1 resolved market" }));

    await screen.findByText(/settled on No/);
    // `0.0 pp` would say the market did not move and "no coverage" that the archive has a
    // hole. The truth is a third thing: there is nothing left to measure.
    expect(screen.queryByText("0.0 pp")).not.toBeInTheDocument();
    expect(screen.queryByText(/no coverage/i)).not.toBeInTheDocument();
  });

  it("says so when every market of an event has resolved", async () => {
    const over = event({
      collection: { state: "resolved", lastSampleAt: new Date(), reason: "every market resolved" },
      markets: [
        {
          id: 2,
          question: "Cut in August?",
          label: "August 6",
          negRisk: false,
          resolvedOutcome: "No",
          outcomes: [outcome(3, "Yes", 0), outcome(4, "No", 1)],
        },
      ],
    });

    render(<PolymarketView api={fakeApi({ listEvents: async () => [over] })} />);
    await unfold();

    expect(await screen.findByText(/every market of this event has resolved/i)).toBeInTheDocument();
    expect(screen.getByText(/what was collected is still here/i)).toBeInTheDocument();
  });

  it("draws the probability as well as writing it, and draws nothing when there is none", async () => {
    const blank = event({
      markets: [
        {
          id: 4,
          question: "Will the Fed cut in March?",
          label: null,
          negRisk: false,
          resolvedOutcome: null,
          outcomes: [outcome(7, "Yes", 0.62), outcome(8, "No", null)],
        },
      ],
    });

    render(<PolymarketView api={fakeApi({ listEvents: async () => [blank] })} />);
    await unfold();

    const meters = await screen.findAllByRole("meter");
    expect(meters).toHaveLength(1);
    expect(meters[0]).toHaveAttribute("aria-valuenow", "0.62");
    // A zero-length bar would read as "zero", which is a claim about the market where the
    // truth is that nothing has been collected.
    expect(screen.getByText(/not collected yet/i)).toBeInTheDocument();
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
