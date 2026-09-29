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
    content: "Brent rose two percent.\n\nAnalysts point to supply.",
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
  it("opens on the last 4 h with the delay as a range and the count named", async () => {
    render(<NewsScreen api={api([item()])} />);

    expect(await screen.findByText("Oil jumps on supply fears")).toBeInTheDocument();
    expect(screen.getByText("Delay 3–5 min")).toBeInTheDocument();
    expect(screen.getByText(/1 · last 4 h/)).toBeInTheDocument();
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

    expect(await screen.findByText("No headlines in the last 4 h.")).toBeInTheDocument();
  });

  it("expands the whole text in place and offers the original only then", async () => {
    render(<NewsScreen api={api([item()])} />);
    const toggle = await screen.findByRole("button", { name: /Oil jumps on supply fears/ });
    expect(screen.queryByRole("link", { name: "Open original" })).not.toBeInTheDocument();

    await userEvent.click(toggle);

    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/Analysts point to supply/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open original" })).toHaveAttribute("target", "_blank");
    expect(screen.queryByText(/carries only a lead/)).not.toBeInTheDocument();
  });

  it("says the feed carried only a lead when there is no body", async () => {
    render(<NewsScreen api={api([item({ content: "" })])} />);

    await userEvent.click(await screen.findByRole("button", { name: /Oil jumps on supply fears/ }));

    expect(screen.getByText(/The feed carries only a lead/)).toBeInTheDocument();
  });

  it("does not toggle the card when it is kept", async () => {
    render(<NewsScreen api={api([item()])} />);
    await screen.findByText("Oil jumps on supply fears");

    await userEvent.click(screen.getByRole("button", { name: "Keep" }));

    expect(screen.getByRole("button", { name: /Oil jumps on supply fears/ })).toHaveAttribute("aria-expanded", "false");
  });

  it("asks for minutes and a bigger limit when the window is a week", async () => {
    const client = api([item()]);
    render(<NewsScreen api={client} />);
    await screen.findByText("Oil jumps on supply fears");
    expect(client.getNews).toHaveBeenLastCalledWith({ minutes: 240, q: undefined, limit: 300 }, expect.anything());

    await userEvent.click(screen.getByRole("button", { name: "7d" }));

    expect(client.getNews).toHaveBeenLastCalledWith({ minutes: 10080, q: undefined, limit: 1000 }, expect.anything());
    expect(await screen.findByText(/last 7 d/)).toBeInTheDocument();
  });

  it("reverses the order with the direction toggle", async () => {
    const older = item({ externalId: "2", title: "Older story", publishedAt: new Date(Date.now() - 60 * 60_000) });
    render(<NewsScreen api={api([older, item()])} />);
    await screen.findByText("Older story");
    const order = () => screen.getAllByRole("button", { name: /story|supply fears/ }).map((b) => b.textContent);
    expect(order()[0]).toMatch(/Oil jumps/);

    await userEvent.click(screen.getByRole("button", { name: "Sort direction" }));

    expect(order()[0]).toMatch(/Older story/);
  });
});
