import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { queryClient } from "../data/query";
import { MarketDataError } from "../data/types";
import { NewsView } from "./NewsView";
import type { NewsApi, NewsItem, NewsSource } from "./newsApi";

/** The tab from the operator's seat: the delay on the card, keeping a headline, and an empty list that says why. */

function item(overrides: Partial<NewsItem> = {}): NewsItem {
  return {
    source: "aljazeera",
    externalId: "1",
    publisher: "Al Jazeera",
    title: "US-Iran talks in New York",
    summary: "Delegations met.",
    content: "",
    url: "https://example.com/1",
    publishedAt: new Date("2026-09-29T15:09:00Z"),
    firstSeenAt: new Date("2026-09-29T15:14:00Z"),
    delayMinSeconds: 180,
    delayMaxSeconds: 300,
    delayUnmeasured: null,
    keptAt: null,
    expiresAt: new Date("2026-10-27T15:14:00Z"),
    ...overrides,
  };
}

function source(overrides: Partial<NewsSource> = {}): NewsSource {
  return {
    source: "aljazeera",
    publisher: "Al Jazeera",
    intervalSeconds: 120,
    status: "ok",
    lastSuccessAt: new Date("2026-09-29T15:14:00Z"),
    lastFailure: null,
    newestPublishedAt: new Date("2026-09-29T15:09:00Z"),
    items24h: 10,
    unmeasured24h: 0,
    feed: { medianSeconds: 100, p90Seconds: 200 },
    waited: { medianSeconds: 160, p90Seconds: 300 },
    ...overrides,
  };
}

function api(items: NewsItem[], overrides: Partial<NewsApi> = {}, sources = [source()]): NewsApi {
  return {
    news: vi.fn(async () => ({ items, truncated: false, windowFrom: new Date() })),
    sources: vi.fn(async () => sources),
    keep: vi.fn(async (_s, _e, keep) => item({ keptAt: keep ? new Date() : null })),
    ...overrides,
  };
}

describe("NewsView", () => {
  it("shows a headline with its delay as a range and names the window", async () => {
    render(<NewsView api={api([item()])} />);

    expect(await screen.findByText("US-Iran talks in New York")).toBeInTheDocument();
    expect(screen.getByText(/opóźnienie 3–5 min/)).toBeInTheDocument();
    expect(screen.getByText(/ostatnie 4 h/)).toBeInTheDocument();
  });

  it("opens the whole news in place and does not send the operator to the site", async () => {
    render(
      <NewsView
        api={api([item({ content: "First paragraph.\n\nSecond paragraph, further in." })])}
      />,
    );

    const toggle = await screen.findByRole("button", { name: /US-Iran talks in New York/ });
    // The title is not a link: the click is for reading here.
    expect(screen.queryByRole("link", { name: /US-Iran talks/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/Second paragraph, further in/)).not.toBeInTheDocument();

    await userEvent.click(toggle);

    expect(screen.getByText(/Second paragraph, further in/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "otwórz oryginał" })).toHaveAttribute("target", "_blank");
    expect(screen.queryByText(/tylko zajawkę/)).not.toBeInTheDocument();
  });

  it("says when the feed carried only a lead, and shows that lead in full", async () => {
    render(<NewsView api={api([item({ summary: "Just the lead.", content: "" })])} />);

    await userEvent.click(await screen.findByRole("button", { name: /US-Iran talks in New York/ }));

    expect(screen.getByText("Just the lead.")).toBeInTheDocument();
    expect(screen.getByText(/Feed niesie tylko zajawkę/)).toBeInTheDocument();
  });

  it("does not open the news when the keep button is pressed", async () => {
    render(<NewsView api={api([item({ content: "Body text." })])} />);

    await userEvent.click(await screen.findByRole("button", { name: "zachowaj" }));

    expect(screen.queryByText("Body text.")).not.toBeInTheDocument();
  });

  it("offers the windows from five minutes to a week and asks for the one chosen", async () => {
    const client = api([item()]);
    render(<NewsView api={client} />);
    await screen.findByText("US-Iran talks in New York");

    for (const label of ["5 min", "15 min", "1 h", "4 h", "24 h", "7 d"]) {
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    }
    await userEvent.click(screen.getByRole("button", { name: "7 d" }));

    await waitFor(() =>
      expect(client.news).toHaveBeenLastCalledWith(
        expect.objectContaining({ minutes: 10080 }),
        expect.anything(),
      ),
    );
    expect(await screen.findByText(/ostatnie 7 d/)).toBeInTheDocument();
  });

  it("switches every source off and on with one click, and says so when none is chosen", async () => {
    const client = api([item()], {}, [source(), source({ source: "irna", publisher: "IRNA" })]);
    render(<NewsView api={client} />);
    await screen.findByText("US-Iran talks in New York");

    await userEvent.click(screen.getByRole("button", { name: "Żadne" }));

    expect(await screen.findByText(/Nie wybrano żadnego źródła/)).toBeInTheDocument();
    const asked = vi.mocked(client.news).mock.calls.length;
    await new Promise((resolve) => setTimeout(resolve, 50));
    // Choosing none is never asked of the server: an empty list of sources means all of them there.
    expect(vi.mocked(client.news).mock.calls.length).toBe(asked);

    await userEvent.click(screen.getByRole("button", { name: "Wszystkie" }));

    expect(await screen.findByText("US-Iran talks in New York")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^aljazeera/ })).toHaveAttribute("aria-pressed", "true");
  });

  it("keeps only the sources that answer with one click", async () => {
    const client = api([item()], {}, [
      source(),
      source({ source: "irna", publisher: "IRNA", status: "failing" }),
    ]);
    render(<NewsView api={client} />);
    await screen.findByText("US-Iran talks in New York");

    await userEvent.click(screen.getByRole("button", { name: "Tylko działające" }));

    expect(screen.getByRole("button", { name: /^aljazeera/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /^irna/ })).toHaveAttribute("aria-pressed", "false");
  });

  it("orders by the wait when asked, and flips the direction", async () => {
    const client = api([
      item({ externalId: "quick", title: "Quick one", delayMaxSeconds: 30 }),
      item({ externalId: "slow", title: "Slow one", delayMaxSeconds: 3000 }),
    ]);
    render(<NewsView api={client} />);
    await screen.findByText("Quick one");

    await userEvent.click(screen.getByRole("button", { name: "czekaliśmy" }));
    const titles = () => screen.getAllByRole("button", { expanded: false }).map((b) => b.textContent ?? "");

    expect(titles()[0]).toMatch(/Slow one/);

    await userEvent.click(screen.getByRole("button", { name: "↓ najdłużej" }));

    expect(titles()[0]).toMatch(/Quick one/);
  });

  it("says why a headline has no delay instead of showing a zero", async () => {
    render(
      <NewsView
        api={api([item({ delayMinSeconds: null, delayMaxSeconds: null, delayUnmeasured: "found_there" })])}
      />,
    );

    expect(await screen.findByText(/zastany przy pierwszym pobraniu/)).toBeInTheDocument();
  });

  it("keeps a headline with one click and asks for it by the pair", async () => {
    const client = api([item()]);
    render(<NewsView api={client} />);

    await userEvent.click(await screen.findByRole("button", { name: "zachowaj" }));

    expect(client.keep).toHaveBeenCalledWith("aljazeera", "1", true, expect.anything());
    expect(await screen.findByRole("button", { name: "zachowany" })).toBeInTheDocument();
  });

  it("puts the headline back as it was, and says so, when keeping is refused", async () => {
    const client = api([item()], {
      keep: vi.fn(async () => {
        throw new MarketDataError("refused", "no");
      }),
    });
    render(<NewsView api={client} />);

    await userEvent.click(await screen.findByRole("button", { name: "zachowaj" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/stan sprzed kliknięcia/);
    expect(screen.getByRole("button", { name: "zachowaj" })).toBeInTheDocument();
  });

  it("says collection has stopped rather than letting an empty list speak for it", async () => {
    render(
      <NewsView
        api={api([], {}, [source({ status: "stale", lastFailure: "refused: HTTP 403" })])}
      />,
    );

    expect(await screen.findByText(/Zbiór stoi/)).toBeInTheDocument();
    expect(screen.getByText(/refused: HTTP 403/)).toBeInTheDocument();
  });

  it("says the list is cut instead of pretending to show the whole window", async () => {
    const client = api([item()], {
      news: vi.fn(async () => ({ items: [item()], truncated: true, windowFrom: null })),
    });
    render(<NewsView api={client} />);

    expect(await screen.findByText(/Lista jest obcięta/)).toBeInTheDocument();
  });

  it("flags a refusing source in the table with its reason and its last success", async () => {
    render(
      <NewsView
        api={api([item()], {}, [
          source(),
          source({
            source: "irna",
            publisher: "IRNA",
            status: "failing",
            lastFailure: "refused: HTTP 403",
            lastSuccessAt: new Date("2026-09-29T14:00:00Z"),
          }),
        ])}
      />,
    );

    await userEvent.click(await screen.findByRole("button", { name: /Źródła i ich opóźnienia/ }));

    const row = screen.getByRole("row", { name: /IRNA/ });
    expect(row).toHaveTextContent("ostatnie pobranie nieudane");
    expect(row).toHaveTextContent("refused: HTTP 403");
    const healthy = screen.getByRole("row", { name: /Al Jazeera/ });
    expect(healthy).toHaveTextContent("działa");
    // Both bounds as median / p90: how late the feed is, then what the operator waited.
    expect(healthy).toHaveTextContent("2 min / 3 min");
    expect(healthy).toHaveTextContent("3 min / 5 min");
  });

  it("keeps the headlines on screen when a refresh fails", async () => {
    let calls = 0;
    const client = api([], {
      news: vi.fn(async () => {
        calls += 1;
        if (calls > 1) throw new MarketDataError("unreachable", "down");
        return { items: [item()], truncated: false, windowFrom: null };
      }),
    });
    render(<NewsView api={client} />);
    await screen.findByText("US-Iran talks in New York");

    await act(async () => {
      await queryClient.refetchQueries({ queryKey: ["news", "items"] });
    });

    await waitFor(() => expect(client.news).toHaveBeenCalledTimes(2));
    expect(screen.getByText("US-Iran talks in New York")).toBeInTheDocument();
  });
});
