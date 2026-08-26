import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MarketDataError } from "../data/types";
import { OutcomeHistory } from "./OutcomeHistory";

// The real library draws to a canvas jsdom cannot render, reaching into a null 2d context inside a
// `requestAnimationFrame` that surfaces after the test that triggered it has finished.
vi.mock("./ProbabilityChart", () => ({
  ProbabilityChart: () => null,
}));

import type { History, PolymarketApi, TrackedEvent } from "./polymarketApi";

/**
 * What the panel says, rather than what the canvas draws: the outcome picker, the range, and the sentence that
 * has to appear when the range reaches back past everything collected. The gap rule is `series.test.ts`.
 */

const EVENT: TrackedEvent = {
  id: 1,
  providerEventId: "0xabc",
  slug: "who-wins",
  title: "Who wins",
  url: "https://polymarket.com/event/who-wins",
  group: null,
  trackedAt: new Date(),
  collection: { state: "collecting", lastSampleAt: new Date(), reason: null },
  markets: [
    {
      id: 4,
      question: "Who wins the nomination?",
      label: "Democratic nominee",
      negRisk: true,
      resolvedOutcome: null,
      outcomes: [
        { id: 7, name: "Newsom", price: 0.31, priceAt: new Date(), lastTrade: null, collectedFrom: null },
        { id: 8, name: "Harris", price: 0.19, priceAt: new Date(), lastTrade: null, collectedFrom: null },
      ],
    },
  ],
};

function history(overrides: Partial<History> = {}): History {
  return { outcomeId: 7, points: [], collectedFrom: null, collectedTo: null, ...overrides };
}

function fakeApi(read: PolymarketApi["history"]): PolymarketApi {
  return {
    listEvents: async () => [],
    readEvent: async () => EVENT,
    snapshot: async () => [],
    changes: async () => ({ eventId: 1, outcomes: [] }),
    history: read,
    trackEvent: async () => ({ event: EVENT, alreadyTracked: false }),
    removeEvent: async () => {},
    listGroups: async () => [],
    createGroup: async () => ({ id: 1, name: "g", eventCount: 0 }),
    deleteGroup: async () => {},
    assignGroup: async () => {},
  };
}

describe("OutcomeHistory", () => {
  it("offers every outcome of every market, named by which market it belongs to", async () => {
    render(<OutcomeHistory client={fakeApi(async () => history())} event={EVENT} />);

    const picker = await screen.findByLabelText("Outcome");
    expect(picker).toHaveDisplayValue("Democratic nominee · Newsom");
    expect(screen.getByRole("option", { name: "Democratic nominee · Harris" })).toBeInTheDocument();
  });

  it("says when the range reaches back past everything that was ever collected", async () => {
    const read = vi.fn<PolymarketApi["history"]>(async () =>
      history({ collectedFrom: new Date("2026-08-19T12:00:00Z"), points: [] }),
    );
    render(<OutcomeHistory client={fakeApi(read)} event={EVENT} />);

    // The default range is 30 days and the archive holds three, so the boundary is not
    // something to infer from a short line — it is said.
    expect(await screen.findByText(/collected only from/i)).toBeInTheDocument();
    expect(screen.getByText(/does not give back a resolved market/i)).toBeInTheDocument();
  });

  it("stays quiet about the boundary when the whole range is covered", async () => {
    render(
      <OutcomeHistory
        client={fakeApi(async () => history({ collectedFrom: new Date("2020-01-01T00:00:00Z") }))}
        event={EVENT}
      />,
    );

    await waitFor(() => expect(screen.queryByText(/collected only from/i)).not.toBeInTheDocument());
  });

  it("asks the module for the range the operator picked", async () => {
    const read = vi.fn<PolymarketApi["history"]>(async () => history());
    render(<OutcomeHistory client={fakeApi(read)} event={EVENT} />);

    await userEvent.click(await screen.findByRole("button", { name: "7d" }));

    await waitFor(() => {
      const last = read.mock.calls.at(-1);
      expect(last?.[0]).toBe(7);
      expect(last?.[2]?.since).toBeInstanceOf(Date);
    });
  });

  it("asks for no boundary at all when the operator wants everything", async () => {
    const read = vi.fn<PolymarketApi["history"]>(async () => history());
    render(<OutcomeHistory client={fakeApi(read)} event={EVENT} />);

    await userEvent.click(await screen.findByRole("button", { name: "all" }));

    await waitFor(() => expect(read.mock.calls.at(-1)?.[2]?.since).toBeUndefined());
  });

  it("reports a failed read instead of drawing an empty chart as if it were the answer", async () => {
    render(
      <OutcomeHistory
        client={fakeApi(async () => {
          throw new MarketDataError("unreachable", "polymarket-data is not reachable");
        })}
        event={EVENT}
      />,
    );

    expect(await screen.findByText(/series could not be read/i)).toBeInTheDocument();
  });
});
