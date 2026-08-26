import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MarketDataError } from "../data/types";
import { RemoveEventDialog } from "./RemoveEventDialog";
import type { PolymarketApi, TrackedEvent } from "./polymarketApi";

/**
 * The one irreversible act the terminal offers, and the only door to it anywhere: no tool the model holds removes
 * an observation. The first test is about wording, because wording is what the requirement is made of.
 */

const EVENT: TrackedEvent = {
  id: 1,
  providerEventId: "0xabc",
  slug: "fed-cuts-in-march",
  title: "Fed cuts in March",
  url: "https://polymarket.com/event/fed-cuts-in-march",
  group: null,
  trackedAt: new Date(),
  collection: { state: "collecting", lastSampleAt: new Date(), reason: null },
  markets: [],
};

function fakeApi(removeEvent: PolymarketApi["removeEvent"]): PolymarketApi {
  return {
    listEvents: async () => [EVENT],
    readEvent: async () => EVENT,
    snapshot: async () => [],
    changes: async () => ({ eventId: 1, outcomes: [] }),
    history: async () => ({ outcomeId: 7, points: [], collectedFrom: null, collectedTo: null }),
    trackEvent: async () => ({ event: EVENT, alreadyTracked: false }),
    removeEvent,
    listGroups: async () => [],
    createGroup: async () => ({ id: 1, name: "g", eventCount: 0 }),
    deleteGroup: async () => {},
    assignGroup: async () => {},
  };
}

describe("RemoveEventDialog", () => {
  it("names the scope and says why this one really cannot be undone", async () => {
    render(
      <RemoveEventDialog
        client={fakeApi(async () => {})}
        event={EVENT}
        onClose={() => {}}
        onRemoved={() => {}}
      />,
    );

    expect(screen.getByText(/every market, every outcome/i)).toBeInTheDocument();
    // A deleted candle can be fetched again; this cannot, and the dialog says which kind
    // of irreversible it is rather than the sentence everybody has learned to click past.
    expect(screen.getByText(/cannot be collected again at any price/i)).toBeInTheDocument();
    expect(screen.getByText(/does not return the history of a market that has resolved/i))
      .toBeInTheDocument();
    // And says what tracking it again would get you, since that is the question this
    // wording used to answer by pointing at a second button that no longer exists.
    expect(screen.getByText(/starts from an empty archive/i)).toBeInTheDocument();
  });

  it("does not offer stopping instead, because there is no such thing", async () => {
    render(
      <RemoveEventDialog
        client={fakeApi(async () => {})}
        event={EVENT}
        onClose={() => {}}
        onRemoved={() => {}}
      />,
    );

    expect(screen.queryByText(/without losing anything/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /stop/i })).not.toBeInTheDocument();
  });

  it("removes the observation and tells the list to re-read", async () => {
    const removeEvent = vi.fn(async () => {});
    const onRemoved = vi.fn();
    render(
      <RemoveEventDialog
        client={fakeApi(removeEvent)}
        event={EVENT}
        onClose={() => {}}
        onRemoved={onRemoved}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Remove" }));

    await waitFor(() => expect(removeEvent).toHaveBeenCalledWith("0xabc", expect.anything()));
    expect(onRemoved).toHaveBeenCalled();
  });

  it("removes nothing when the operator backs out", async () => {
    const removeEvent = vi.fn(async () => {});
    const onClose = vi.fn();
    render(
      <RemoveEventDialog
        client={fakeApi(removeEvent)}
        event={EVENT}
        onClose={onClose}
        onRemoved={() => {}}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(removeEvent).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("keeps a refusal beside the decision rather than closing on it", async () => {
    render(
      <RemoveEventDialog
        client={fakeApi(async () => {
          throw new MarketDataError("refused", "caller may not reach the REST contract");
        })}
        event={EVENT}
        onClose={() => {}}
        onRemoved={() => {}}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Remove" }));

    expect(await screen.findByText(/caller may not reach the REST contract/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove" })).toBeInTheDocument();
  });
});
