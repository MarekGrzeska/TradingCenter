import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MarketDataError } from "../data/types";

// One part, one controllable failure. The suite is about how a refusal is *named* in the top bar, so the
// source is a stub whose ping rejects with whatever the case under test is about.
let pingFailure: unknown = null;

vi.mock("../data/marketData", () => ({
  marketData: {
    parts: [
      {
        id: "archive",
        label: "market-data",
        whenUnreachable: "the candles on screen are stale",
        ping: async () => {
          if (pingFailure) throw pingFailure;
        },
      },
    ],
  },
  identity: {
    state: () => "signed-out",
    subscribe: () => () => {},
    token: async () => null,
    refresh: async () => null,
    signIn: () => {},
  },
}));

const { TopBar } = await import("./TopBar");

describe("TopBar source health (terminal-shell spec)", () => {
  it("calls a back end that refuses for want of a session 'needs sign-in', not 'unreachable'", async () => {
    // The regression this file exists for: both back ends were reported unreachable while both were
    // healthy — the operator was simply signed out, and every ping failed before a request was sent.
    pingFailure = new MarketDataError("unauthenticated", "you are signed out");
    render(<TopBar />);

    expect(await screen.findByText(/market-data needs sign-in/i)).toBeInTheDocument();
    expect(screen.queryByText(/market-data unreachable/i)).not.toBeInTheDocument();
    // The consequence line belongs to a source that is actually down. Saying the candles are stale
    // *because the archive is unreachable* is the false claim, not the staleness.
    expect(screen.queryByText(/the candles on screen are stale/i)).not.toBeInTheDocument();
  });

  it("still reports a back end that is genuinely down as unreachable", async () => {
    pingFailure = new MarketDataError("unreachable", "connection refused");
    render(<TopBar />);

    expect(await screen.findByText(/market-data unreachable/i)).toBeInTheDocument();
    expect(screen.getByText(/the candles on screen are stale/i)).toBeInTheDocument();
  });

  it("reports a failure it cannot classify as unreachable rather than as a session problem", async () => {
    // A bare `Error` is what a transport blowing up looks like. Guessing "signed out" from it would send
    // the operator to a sign-in that fixes nothing.
    pingFailure = new TypeError("Failed to fetch");
    render(<TopBar />);

    expect(await screen.findByText(/market-data unreachable/i)).toBeInTheDocument();
  });

  it("says the source answered when it does", async () => {
    pingFailure = null;
    render(<TopBar />);

    expect(await screen.findByText(/market-data connected/i)).toBeInTheDocument();
  });
});
