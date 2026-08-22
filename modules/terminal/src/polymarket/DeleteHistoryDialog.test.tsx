import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MarketDataError } from "../data/types";
import { DeleteHistoryDialog } from "./DeleteHistoryDialog";
import type { PolymarketApi, TrackedEvent } from "./polymarketApi";

/**
 * The one irreversible act the terminal offers, and the only door to it anywhere: no tool
 * the model holds deletes a sample. Three tests, and the first of them is about wording,
 * because wording is what the requirement is made of.
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

function fakeApi(deleteHistory: PolymarketApi["deleteHistory"]): PolymarketApi {
  return {
    listEvents: async () => [EVENT],
    readEvent: async () => EVENT,
    snapshot: async () => [],
    changes: async () => ({ eventId: 1, outcomes: [] }),
    history: async () => ({ outcomeId: 7, points: [], collectedFrom: null, collectedTo: null }),
    trackEvent: async () => ({ event: EVENT, alreadyTracked: false }),
    endTracking: async () => EVENT,
    deleteHistory,
    listGroups: async () => [],
    createGroup: async () => ({ id: 1, name: "g", eventCount: 0 }),
    deleteGroup: async () => {},
    assignGroup: async () => {},
  };
}

describe("DeleteHistoryDialog", () => {
  it("names the scope and says why this one really cannot be undone", async () => {
    render(
      <DeleteHistoryDialog
        client={fakeApi(async () => ({ samplesDeleted: 0, rangesDeleted: 0 }))}
        event={EVENT}
        onClose={() => {}}
        onDeleted={() => {}}
      />,
    );

    expect(screen.getByText(/every market, every outcome/i)).toBeInTheDocument();
    // A deleted candle can be fetched again; this cannot, and the dialog says which kind
    // of irreversible it is rather than the sentence everybody has learned to click past.
    expect(screen.getByText(/cannot be collected again at any price/i)).toBeInTheDocument();
    expect(screen.getByText(/does not return the history of a market that has resolved/i))
      .toBeInTheDocument();
    // And points at the reversible thing next to it, which is what most people want.
    expect(screen.getByText(/without losing anything/i)).toBeInTheDocument();
  });

  it("removes it and says how much went", async () => {
    const deleteHistory = vi.fn(async () => ({ samplesDeleted: 4_120, rangesDeleted: 7 }));
    const onDeleted = vi.fn();
    render(
      <DeleteHistoryDialog
        client={fakeApi(deleteHistory)}
        event={EVENT}
        onClose={() => {}}
        onDeleted={onDeleted}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Remove history" }));

    await waitFor(() => expect(deleteHistory).toHaveBeenCalledWith("0xabc", expect.anything()));
    expect(onDeleted).toHaveBeenCalled();
    expect(await screen.findByText(/4120 sample\(s\) and 7 collected range\(s\)/i))
      .toBeInTheDocument();
    expect(screen.getByText(/still tracked/i)).toBeInTheDocument();
  });

  it("removes nothing when the operator backs out", async () => {
    const deleteHistory = vi.fn(async () => ({ samplesDeleted: 0, rangesDeleted: 0 }));
    const onClose = vi.fn();
    render(
      <DeleteHistoryDialog
        client={fakeApi(deleteHistory)}
        event={EVENT}
        onClose={onClose}
        onDeleted={() => {}}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(deleteHistory).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("keeps a refusal beside the decision rather than closing on it", async () => {
    render(
      <DeleteHistoryDialog
        client={fakeApi(async () => {
          throw new MarketDataError("refused", "caller may not reach the REST contract");
        })}
        event={EVENT}
        onClose={() => {}}
        onDeleted={() => {}}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Remove history" }));

    expect(await screen.findByText(/caller may not reach the REST contract/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove history" })).toBeInTheDocument();
  });
});
