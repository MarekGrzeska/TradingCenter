import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// These tests are about the shell — routing, the tab registry, the source
// indicator. The Graph tab's real grid would mount charts (and with them a
// canvas jsdom cannot provide, plus a live mock feed) for every assertion
// about a link. GridView has its own tests.
vi.mock("./grid/GridView", () => ({
  GridView: () => <div>grid stub</div>,
}));

const { App } = await import("./App");
const { sourceStore } = await import("./data/sourceStore");

beforeEach(() => {
  window.history.pushState({}, "", "/");
});

// sourceStore is a module-level singleton (one active source for the whole
// app, by design) — reset it so a source switch in one test can't leak into
// the next.
afterEach(() => {
  sourceStore.setSource("mock");
});

// The top bar's health check (useSourceHealth) resolves asynchronously right
// after mount regardless of what a test cares about — waiting for it once
// keeps that update inside `act()` instead of leaking a warning into
// whichever test happens to be running when the microtask lands.
async function renderApp() {
  const view = render(<App />);
  await screen.findByText(/checking|connected|unreachable/i);
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
    // Matches the ComingSoon placeholder's own heading, not the nav link of
    // the same name.
    expect(screen.getByText("Instruments", { selector: "p" })).toBeInTheDocument();
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
  it("names the active source and reports it reachable once the mock source answers", async () => {
    await renderApp();
    expect(await screen.findByText(/mock connected/i)).toBeInTheDocument();
  });

  it("switching source updates the label and re-checks reachability", async () => {
    const user = userEvent.setup();
    await renderApp();
    await screen.findByText(/mock connected/i);

    await user.selectOptions(screen.getByLabelText("Source"), "gateway");

    // No real gateway is running in this test — the point is that the
    // indicator follows the newly selected source rather than staying on
    // the old one's last known state.
    expect(await screen.findByText(/gateway (unreachable|checking)/i)).toBeInTheDocument();
  });
});
