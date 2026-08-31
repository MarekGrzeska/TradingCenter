import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { queryClient } from "../data/query";
import { MarketDataError } from "../data/types";
import { SocialView } from "./SocialView";
import type { ArchiveState, Post, PostsPage, SocialApi } from "./socialApi";

/**
 * The tab from the operator's seat: that a scored post is in front, that the rest is one fold away, and that an
 * empty list is never the answer to three different questions.
 */

function post(overrides: Partial<Post> = {}): Post {
  return {
    source: "truth_social",
    externalId: "1",
    author: "realDonaldTrump",
    content: "TARIFFS ON CHINA START MONDAY.",
    url: "https://trumpstruth.org/statuses/1",
    isRepost: false,
    publishedAt: new Date("2026-08-31T10:00:00Z"),
    translatedContent: null,
    topics: [],
    impactScore: null,
    analysedModel: null,
    analysedAt: null,
    ...overrides,
  };
}

function state(overrides: Partial<ArchiveState> = {}): ArchiveState {
  return {
    sources: [
      {
        source: "truth_social",
        collectingSince: new Date("2026-08-30T00:00:00Z"),
        lastSuccessAt: new Date("2026-08-31T10:05:00Z"),
        lastFailureReason: null,
        stale: false,
      },
    ],
    postsInWindow: 1,
    windowHours: 24,
    modelConfigured: true,
    ...overrides,
  };
}

function api(posts: Post[], overrides: Partial<SocialApi> = {}): SocialApi {
  const page: PostsPage = {
    posts,
    windowFrom: new Date("2026-08-30T10:00:00Z"),
    windowTo: new Date("2026-08-31T10:00:00Z"),
  };
  return {
    recentPosts: vi.fn(async () => page),
    state: vi.fn(async () => state()),
    ...overrides,
  };
}

describe("SocialView", () => {
  it("shows a scored post without a click and folds the rest away", async () => {
    render(
      <SocialView
        api={api([
          post({ externalId: "big", content: "TARIFFS.", impactScore: 9, analysedModel: "m" }),
          post({ externalId: "small", content: "GREAT ROUND OF GOLF.", impactScore: 2 }),
        ])}
      />,
    );

    expect(await screen.findByText("TARIFFS.")).toBeInTheDocument();
    expect(screen.queryByText("GREAT ROUND OF GOLF.")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /Pozostałe posty \(1\)/ }));

    expect(screen.getByText("GREAT ROUND OF GOLF.")).toBeInTheDocument();
  });

  it("says a day held nothing scored rather than looking empty", async () => {
    render(<SocialView api={api([post({ impactScore: 2 })])} />);

    expect(await screen.findByText(/Nic o wpływie 6\/10 lub wyższym/)).toBeInTheDocument();
  });

  it("shows the Polish reading when there is one and the original when there is not", async () => {
    render(
      <SocialView
        api={api([
          post({ externalId: "pl", impactScore: 8, translatedContent: "CŁA NA CHINY OD PONIEDZIAŁKU." }),
          post({ externalId: "en", impactScore: 7, content: "THE FED MUST CUT." }),
        ])}
      />,
    );

    expect(await screen.findByText("CŁA NA CHINY OD PONIEDZIAŁKU.")).toBeInTheDocument();
    expect(screen.getByText("THE FED MUST CUT.")).toBeInTheDocument();
  });

  it("names a stalled archive instead of letting an empty list speak for it", async () => {
    const client = api([], {
      state: vi.fn(async () =>
        state({
          sources: [
            {
              source: "truth_social",
              collectingSince: new Date("2026-08-30T00:00:00Z"),
              lastSuccessAt: new Date("2026-08-31T04:00:00Z"),
              lastFailureReason: "the feed did not answer",
              stale: true,
            },
          ],
          postsInWindow: 0,
        }),
      ),
    });

    render(<SocialView api={client} />);

    expect(await screen.findByText(/Archiwum nie zebrało nic z truth_social/)).toBeInTheDocument();
    expect(screen.getByText(/the feed did not answer/)).toBeInTheDocument();
  });

  it("says the readings are off rather than showing posts with no explanation", async () => {
    const client = api([post({ impactScore: null })], {
      state: vi.fn(async () => state({ modelConfigured: false })),
    });

    render(<SocialView api={client} />);

    expect(await screen.findByText(/Model nie jest skonfigurowany/)).toBeInTheDocument();
  });

  it("keeps the posts on screen when a refresh fails, and says the read failed", async () => {
    let calls = 0;
    const client = api([]);
    client.recentPosts = vi.fn(async () => {
      calls += 1;
      if (calls > 1) throw new MarketDataError("unreachable", "social-data is not reachable");
      return {
        posts: [post({ externalId: "kept", content: "STILL HERE.", impactScore: 8 })],
        windowFrom: new Date("2026-08-30T10:00:00Z"),
        windowTo: new Date("2026-08-31T10:00:00Z"),
      };
    });

    render(<SocialView api={client} />);
    expect(await screen.findByText("STILL HERE.")).toBeInTheDocument();

    // The refresh the poll would have made, asked for directly so the test does not wait a minute.
    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: ["social", "posts", 24] });
    });

    expect(await screen.findByText(/social-data is not reachable/)).toBeInTheDocument();
    expect(screen.getByText("STILL HERE.")).toBeInTheDocument();
  });
});
