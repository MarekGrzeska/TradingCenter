import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ArchiveError } from "../data/http";
import type { NewsApi, NewsItem, NewsSource } from "./api";
import { NewsScreen } from "./NewsScreen";

function item(overrides: Partial<NewsItem> = {}): NewsItem {
  return {
    source: "reuters",
    externalId: "1",
    publisher: "Reuters",
    title: "Oil jumps on supply fears",
    summary: "Brent rose two percent.",
    url: "https://example.com/1",
    publishedAt: new Date(Date.now() - 10 * 60_000),
    firstSeenAt: new Date(Date.now() - 5 * 60_000),
    delayMinSeconds: 180,
    delayMaxSeconds: 300,
    delayUnmeasured: null,
    keptAt: null,
    expiresAt: new Date(Date.now() + 3 * 86_400_000),
    ...overrides,
  };
}

function source(overrides: Partial<NewsSource> = {}): NewsSource {
  return {
    source: "reuters",
    publisher: "Reuters",
    status: "ok",
    lastSuccessAt: new Date(),
    lastFailure: null,
    items24h: 40,
    unmeasured24h: 0,
    delayMinMedianSeconds: 60,
    delayMinP90Seconds: 120,
    delayMaxMedianSeconds: 180,
    delayMaxP90Seconds: 400,
    newestPublishedAt: new Date(),
    ...overrides,
  };
}

function api(items: NewsItem[], overrides: Partial<NewsApi> = {}): NewsApi {
  return {
    getNews: vi.fn(async () => ({ items, count: items.length, truncated: false })),
    getNewsSources: vi.fn(async () => [source()]),
    setKept: vi.fn(async (_s, _e, keep) => item({ keptAt: keep ? new Date() : null, expiresAt: null })),
    ...overrides,
  };
}

describe("NewsScreen", () => {
  it("opens on the last 6 h with the delay as a range and the count named", async () => {
    render(<NewsScreen api={api([item()])} />);

    expect(await screen.findByText("Oil jumps on supply fears")).toBeInTheDocument();
    expect(screen.getByText("Delay 3–5 min")).toBeInTheDocument();
    expect(screen.getByText(/1 · last 6 h/)).toBeInTheDocument();
  });

  it("says why there is no delay instead of showing a blank", async () => {
    const client = api([item({ delayMinSeconds: null, delayMaxSeconds: null, delayUnmeasured: "found_there" })]);

    render(<NewsScreen api={client} />);

    expect(await screen.findByText("Delay found on first fetch")).toBeInTheDocument();
  });

  it("keeps the list on screen when a refresh fails", async () => {
    const getNews = vi
      .fn()
      .mockResolvedValueOnce({ items: [item()], count: 1, truncated: false })
      .mockRejectedValue(new ArchiveError("unreachable", "social-data is not reachable"));
    render(<NewsScreen api={api([], { getNews })} />);
    await screen.findByText("Oil jumps on supply fears");

    await userEvent.click(screen.getByRole("button", { name: /updated/ }));

    expect(await screen.findByText("social-data is not reachable")).toBeInTheDocument();
    expect(screen.getByText("Oil jumps on supply fears")).toBeInTheDocument();
  });

  it("puts the card back and says so when keeping is refused", async () => {
    const setKept = vi.fn(async () => {
      throw new ArchiveError("refused", "the archive refused");
    });
    render(<NewsScreen api={api([item()], { setKept })} />);
    await screen.findByText("Oil jumps on supply fears");

    await userEvent.click(screen.getByRole("button", { name: "Keep" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/the archive refused/);
    expect(screen.getByRole("button", { name: "Keep" })).toHaveAttribute("aria-pressed", "false");
  });

  it("marks the card kept when the write goes through", async () => {
    render(<NewsScreen api={api([item()])} />);
    await screen.findByText("Oil jumps on supply fears");

    await userEvent.click(screen.getByRole("button", { name: "Keep" }));

    expect(await screen.findByRole("button", { name: "Kept", pressed: true })).toBeInTheDocument();
  });

  it("says the collection is stalled rather than showing an empty list", async () => {
    const client = api([], {
      getNewsSources: vi.fn(async () => [source({ status: "stale", lastFailure: "http 403" })]),
    });

    render(<NewsScreen api={client} />);
    await userEvent.click(await screen.findByRole("button", { name: /Sources/ }));

    expect(await screen.findByText(/Collection is stalled/)).toBeInTheDocument();
    expect(screen.getByText(/http 403/)).toBeInTheDocument();
  });

  it("tells a quiet window from a stalled collection", async () => {
    render(<NewsScreen api={api([])} />);

    expect(await screen.findByText("No headlines in the last 6 h.")).toBeInTheDocument();
  });
});
