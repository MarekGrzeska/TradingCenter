import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// These tests are about the shell — routing, the tab registry, the connection
// indicator. The Graph tab's real grid would mount charts (and with them a
// canvas jsdom cannot provide) for every assertion about a link. GridView has
// its own tests.
vi.mock("./grid/GridView", () => ({
  GridView: () => <div>grid stub</div>,
}));
vi.mock("./instruments/InstrumentsView", () => ({
  InstrumentsView: () => <div>instruments stub</div>,
}));
// Neither back end is running under the test suite; both reachability checks
// are stubbed so these tests assert routing, not connectivity.
vi.mock("./data/marketData", () => ({
  marketData: {
    parts: [
      {
        id: "archive",
        label: "market-data",
        whenUnreachable: "the candles on screen are stale",
        ping: async () => {},
      },
      {
        id: "gateway",
        label: "capital-gateway",
        whenUnreachable: "instrument search is unavailable",
        ping: async () => {},
      },
    ],
    searchInstruments: async () => [],
    listInstruments: async () => ({ instruments: [], count: 0, truncated: false }),
    history: async () => [],
    subscribe: () => () => {},
  },
}));

const { App } = await import("./App");

beforeEach(() => {
  window.history.pushState({}, "", "/");
});

// The top bar's health check (useSourceHealth) resolves asynchronously right
// after mount regardless of what a test cares about — waiting for it once
// keeps that update inside `act()` instead of leaking a warning into
// whichever test happens to be running when the microtask lands.
async function renderApp() {
  const view = render(<App />);
  await screen.findByText(/market-data (checking|connected|unreachable)/i);
  return view;
}

describe("App routing (terminal-shell spec)", () => {
  it("redirects the root to the default tab", async () => {
    await renderApp();
    expect(window.location.pathname).toBe("/graph");
  });

  it("switching tabs updates both the content and the address", async () => {
    const user = userEvent.setup();
    await renderApp();

    await user.click(screen.getByRole("link", { name: "Instruments" }));

    expect(window.location.pathname).toBe("/instruments");
    expect(screen.getByText("instruments stub")).toBeInTheDocument();
  });

  it("loading an address directly shows that tab, not the default", async () => {
    window.history.pushState({}, "", "/instruments");
    await renderApp();
    expect(window.location.pathname).toBe("/instruments");
  });

  // `Instruments` absorbed the old `Archive` tab rather than being renamed
  // from it, so a bookmark to the old address must not resolve to anything —
  // a silent redirect would be a second, hidden way to reach the same tab
  // (design.md, "Zakładki: `Archive` znika, `Data History` dochodzi").
  it("sends a stale /archive bookmark to the unknown-tab page, not a tab", async () => {
    window.history.pushState({}, "", "/archive");
    await renderApp();

    expect(screen.getByText(/no tab lives at this address/i)).toBeInTheDocument();
  });

  it("shows an explicit placeholder for a not-yet-implemented tab, other tabs unaffected", async () => {
    const user = userEvent.setup();
    await renderApp();

    // Graph is implemented; Account is one of the registry entries reserved
    // for a later change.
    await user.click(screen.getByRole("link", { name: "Account" }));
    expect(screen.getByText(/isn't built yet/i)).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "Graph" }));
    expect(window.location.pathname).toBe("/graph");
    expect(screen.queryByText(/isn't built yet/i)).not.toBeInTheDocument();
  });

  it("shows a way back to the default tab for an unknown address", async () => {
    window.history.pushState({}, "", "/nope");
    await renderApp();

    expect(screen.getByText(/no tab lives at this address/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /back to graph/i })).toHaveAttribute(
      "href",
      "/graph",
    );
  });
});

describe("App top bar (terminal-shell spec, source status)", () => {
  // Two back ends, two indicators: the archive keeps the candles and the
  // gateway keeps the catalogue, and they go down separately. One combined
  // light would send an operator looking in the wrong place.
  it("names each back end and reports it reachable once it answers", async () => {
    await renderApp();
    expect(await screen.findByText(/market-data connected/i)).toBeInTheDocument();
    expect(await screen.findByText(/capital-gateway connected/i)).toBeInTheDocument();
  });
});
