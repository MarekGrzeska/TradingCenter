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
// No gateway is running under the test suite; the top bar's reachability
// check is stubbed so these tests assert routing, not connectivity.
vi.mock("./data/marketData", () => ({
  marketData: {
    id: "gateway" as const,
    searchInstruments: async () => [],
    listInstruments: async () => ({ instruments: [], count: 0, truncated: false }),
    history: async () => [],
    ping: async () => {},
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
  await screen.findByText(/capital-gateway (checking|connected|unreachable)/i);
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
  it("names the source and reports it reachable once it answers", async () => {
    await renderApp();
    expect(await screen.findByText(/capital-gateway connected/i)).toBeInTheDocument();
  });
});
