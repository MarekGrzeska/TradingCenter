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
vi.mock("./history/CollectionHistoryView", () => ({
  CollectionHistoryView: () => <div>data history stub</div>,
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
  // The unconfigured identity, which is what a local run has: the top bar shows
  // no sign-in state at all, so these tests keep asserting on routing and the
  // two back ends without a third indicator appearing beside them.
  identity: {
    state: () => "unconfigured",
    subscribe: () => () => {},
    token: async () => null,
    refresh: async () => null,
    signIn: () => {},
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

    await user.click(screen.getByRole("link", { name: "Data History" }));

    expect(window.location.pathname).toBe("/data-history");
    expect(screen.getByText("data history stub")).toBeInTheDocument();
  });

  it("loading an address directly shows that tab, not the default", async () => {
    window.history.pushState({}, "", "/instruments");
    await renderApp();
    expect(window.location.pathname).toBe("/instruments");
  });

  // Both tabs this change introduced are addressable, so a reload on either comes back
  // to it (terminal-data-manager and terminal-collection-history specs, "Odświeżenie
  // strony").
  it("comes back to Data History on a reload rather than the default tab", async () => {
    window.history.pushState({}, "", "/data-history");
    await renderApp();

    expect(window.location.pathname).toBe("/data-history");
    expect(screen.getByText("data history stub")).toBeInTheDocument();
  });

  // One tab speaks about instruments, not two: the provider-catalogue browser is gone
  // as a view of its own (terminal-data-manager spec, "Zakładki mówiące o instrumentach").
  it("offers exactly one instruments tab and no catalogue or archive tab beside it", async () => {
    await renderApp();

    expect(screen.getAllByRole("link", { name: "Instruments" })).toHaveLength(1);
    expect(screen.queryByRole("link", { name: "Archive" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Catalogue" })).not.toBeInTheDocument();
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

  // Positions, Orders and Account never shipped a view, so the registry never carried
  // them past that (`terminal-shell` spec, "Rejestr zakładek jest otwarty") — their
  // addresses behave like any other unknown one, not like a placeholder tab.
  it("sends the old placeholder addresses to the unknown-tab page, not a tab", async () => {
    window.history.pushState({}, "", "/account");
    await renderApp();

    expect(screen.getByText(/no tab lives at this address/i)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Account" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Positions" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Orders" })).not.toBeInTheDocument();
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

describe("App agent chat", () => {
  // It belongs to the terminal, not to a tab: the rail is in the same pixels on every one
  // of them, and expansion is the only thing that decides whether the panel is open.
  it("keeps the agent chat reachable from every tab", async () => {
    const user = userEvent.setup();
    await renderApp();

    expect(screen.getByRole("button", { name: /open agent chat/i })).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "Instruments" }));
    await user.click(screen.getByRole("button", { name: /open agent chat/i }));

    expect(screen.getByRole("complementary", { name: /agent chat/i })).toBeInTheDocument();

    // A tab switch re-renders the outlet; the panel is a sibling of it and stays open.
    await user.click(screen.getByRole("link", { name: "Data History" }));

    expect(screen.getByText("data history stub")).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: /agent chat/i })).toBeInTheDocument();
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
