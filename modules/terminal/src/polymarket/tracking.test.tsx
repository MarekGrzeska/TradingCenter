import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MarketDataError } from "../data/types";
import { PolymarketView } from "./PolymarketView";
import type { EventChanges, Group, PolymarketApi, TrackedEvent } from "./polymarketApi";

/**
 * What the operator can change from this tab: the watch list and the groups. Three tests
 * per route — the happy path, an error, and a refusal — because those are the three things
 * a screen has to get right about a write it did not perform itself.
 */

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
        outcomes: [
          {
            id: 7,
            name: "Yes",
            price: 0.62,
            priceAt: new Date(),
            lastTrade: null,
            collectedFrom: null,
          },
        ],
      },
    ],
    ...overrides,
  };
}

const MACRO: Group = { id: 3, name: "macro", eventCount: 1 };

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
    listGroups: async () => [MACRO],
    createGroup: async () => ({ id: 9, name: "elections", eventCount: 0 }),
    deleteGroup: async () => {},
    assignGroup: async () => {},
  };
  return { ...base, ...overrides };
}

async function openTrackDialog() {
  await userEvent.click(await screen.findByRole("button", { name: "Track event" }));
  return screen.getByLabelText(/event address or slug/i);
}

describe("tracking an event", () => {
  it("sends whichever spelling the operator pasted", async () => {
    const trackEvent = vi.fn(async () => ({ event: event(), alreadyTracked: false }));
    render(<PolymarketView api={fakeApi({ trackEvent })} />);

    const field = await openTrackDialog();
    await userEvent.type(field, "https://polymarket.com/event/fed-cuts-in-march");
    await userEvent.click(screen.getByRole("button", { name: "Track" }));

    await waitFor(() =>
      expect(trackEvent).toHaveBeenCalledWith(
        "https://polymarket.com/event/fed-cuts-in-march",
        expect.anything(),
        undefined,
      ),
    );
  });

  it("says an event was already tracked instead of reporting a second observation", async () => {
    render(
      <PolymarketView
        api={fakeApi({
          trackEvent: async () => ({ event: event(), alreadyTracked: true }),
        })}
      />,
    );

    const field = await openTrackDialog();
    await userEvent.type(field, "fed-cuts-in-march");
    await userEvent.click(screen.getByRole("button", { name: "Track" }));

    expect(await screen.findByText(/already under observation/i)).toBeInTheDocument();
    expect(screen.getByText(/collected history is untouched/i)).toBeInTheDocument();
  });

  it("shows the ceiling as a refusal with its reason, beside the decision", async () => {
    render(
      <PolymarketView
        api={fakeApi({
          trackEvent: async () => {
            throw new MarketDataError("refused", "50 events are already tracked; end one first");
          },
        })}
      />,
    );

    const field = await openTrackDialog();
    await userEvent.type(field, "fed-cuts-in-march");
    await userEvent.click(screen.getByRole("button", { name: "Track" }));

    // Beside the decision, not thrown at the view the dialog just left.
    expect(await screen.findByText(/50 events are already tracked/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Track" })).toBeInTheDocument();
  });

  it("cannot be submitted with nothing in the field", async () => {
    render(<PolymarketView api={fakeApi()} />);

    await openTrackDialog();

    expect(screen.getByRole("button", { name: "Track" })).toBeDisabled();
  });
});

describe("ending an observation", () => {
  it("says the collected data stays, before it happens", async () => {
    render(<PolymarketView api={fakeApi()} />);

    await userEvent.click(await screen.findByRole("button", { name: "Stop tracking" }));

    expect(await screen.findByText(/everything already collected stays/i)).toBeInTheDocument();
    expect(screen.getByText(/separate action/i)).toBeInTheDocument();
  });

  it("ends it and reloads the list", async () => {
    const endTracking = vi.fn(async () => event({ collection: { state: "ended", lastSampleAt: null, reason: null } }));
    const listEvents = vi.fn(async () => [event()]);
    render(<PolymarketView api={fakeApi({ endTracking, listEvents })} />);

    await userEvent.click(await screen.findByRole("button", { name: "Stop tracking" }));
    // Two now carry that name — the one in the card and the one in the dialog it opened.
    await userEvent.click(screen.getAllByRole("button", { name: "Stop tracking" }).at(-1)!);

    await waitFor(() => expect(endTracking).toHaveBeenCalledWith("0xabc", expect.anything()));
    await waitFor(() => expect(listEvents.mock.calls.length).toBeGreaterThan(1));
  });

  it("keeps a failure beside the question rather than closing on it", async () => {
    render(
      <PolymarketView
        api={fakeApi({
          endTracking: async () => {
            throw new MarketDataError("unreachable", "polymarket-data is not reachable");
          },
        })}
      />,
    );

    await userEvent.click(await screen.findByRole("button", { name: "Stop tracking" }));
    const confirm = screen.getAllByRole("button", { name: "Stop tracking" }).at(-1)!;
    await userEvent.click(confirm);

    expect(await screen.findByText(/is not reachable/i)).toBeInTheDocument();
  });
});

describe("groups", () => {
  it("creates one and narrows the list to it", async () => {
    const createGroup = vi.fn(async () => ({ id: 9, name: "elections", eventCount: 0 }));
    render(<PolymarketView api={fakeApi({ createGroup })} />);

    await userEvent.click(await screen.findByRole("button", { name: "New group" }));
    await userEvent.type(screen.getByLabelText("Name"), "elections");
    await userEvent.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => expect(createGroup).toHaveBeenCalledWith("elections", expect.anything()));
  });

  it("says deleting a group ends no observation and removes no history", async () => {
    render(<PolymarketView api={fakeApi()} />);

    await userEvent.click(await screen.findByRole("button", { name: /macro/ }));
    await userEvent.click(await screen.findByRole("button", { name: /Delete “macro”/ }));

    expect(await screen.findByText(/stay tracked/i)).toBeInTheDocument();
    expect(screen.getByText(/none of their collected history is removed/i)).toBeInTheDocument();
  });

  it("reports a refusal to delete rather than pretending it worked", async () => {
    render(
      <PolymarketView
        api={fakeApi({
          deleteGroup: async () => {
            throw new MarketDataError("refused", "the group is not yours");
          },
        })}
      />,
    );

    await userEvent.click(await screen.findByRole("button", { name: /macro/ }));
    await userEvent.click(await screen.findByRole("button", { name: /Delete “macro”/ }));
    await userEvent.click(screen.getByRole("button", { name: "Delete group" }));

    expect(await screen.findByText(/the group is not yours/i)).toBeInTheDocument();
  });

  it("takes an event out of every group without ending its observation", async () => {
    const assignGroup = vi.fn(async () => {});
    render(
      <PolymarketView
        api={fakeApi({ assignGroup, listEvents: async () => [event({ group: "macro" })] })}
      />,
    );

    const select = await screen.findByLabelText(/Group for Fed cuts in March/i);
    await userEvent.selectOptions(select, "");

    await waitFor(() => expect(assignGroup).toHaveBeenCalledWith(1, null, expect.anything()));
  });
});
