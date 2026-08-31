import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ArchiveError } from "../data/http";
import type { ArchiveState, Post, SocialApi } from "./api";
import { PostsScreen } from "./PostsScreen";

/**
 * The screen from a thumb's seat: what is open without a tap, what an empty list is allowed to mean,
 * and that a failed read leaves what is on the phone alone.
 */

function post(overrides: Partial<Post> = {}): Post {
  return {
    source: "truth_social",
    externalId: "1",
    content: "TARIFFS ON CHINA START MONDAY.",
    translatedContent: null,
    url: null,
    isRepost: false,
    publishedAt: new Date(Date.now() - 10 * 60_000),
    topics: [],
    impactScore: null,
    analysedModel: null,
    ...overrides,
  };
}

function archive(overrides: Partial<ArchiveState> = {}): ArchiveState {
  return {
    sources: [
      {
        source: "truth_social",
        lastSuccessAt: new Date(Date.now() - 60_000),
        lastFailureReason: null,
        stale: false,
      },
    ],
    windowHours: 24,
    modelConfigured: true,
    ...overrides,
  };
}

function api(posts: Post[], overrides: Partial<SocialApi> = {}): SocialApi {
  return {
    recentPosts: vi.fn(async () => posts),
    state: vi.fn(async () => archive()),
    ...overrides,
  };
}

describe("PostsScreen", () => {
  it("opens on the scored posts and keeps the rest one tap away", async () => {
    render(
      <PostsScreen
        api={api([
          post({ externalId: "big", content: "TARIFFS.", impactScore: 9 }),
          post({ externalId: "small", content: "GREAT ROUND OF GOLF.", impactScore: 2 }),
        ])}
      />,
    );

    expect(await screen.findByText("TARIFFS.")).toBeInTheDocument();
    expect(screen.queryByText("GREAT ROUND OF GOLF.")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /Show the other 1/ }));

    expect(screen.getByText("GREAT ROUND OF GOLF.")).toBeInTheDocument();
  });

  it("shows the Polish reading where the archive has one", async () => {
    render(
      <PostsScreen
        api={api([post({ impactScore: 8, translatedContent: "CŁA NA CHINY OD PONIEDZIAŁKU." })])}
      />,
    );

    expect(await screen.findByText("CŁA NA CHINY OD PONIEDZIAŁKU.")).toBeInTheDocument();
  });

  it("says the archive has stalled rather than letting an empty list say it", async () => {
    const client = api([], {
      state: vi.fn(async () =>
        archive({
          sources: [
            {
              source: "truth_social",
              lastSuccessAt: new Date(Date.now() - 5 * 3_600_000),
              lastFailureReason: "the feed did not answer",
              stale: true,
            },
          ],
        }),
      ),
    });

    render(<PostsScreen api={client} />);

    expect(await screen.findByText(/No posts collected from truth_social/)).toBeInTheDocument();
    expect(screen.getByText(/the feed did not answer/)).toBeInTheDocument();
  });

  it("says the readings are off rather than showing unscored posts unexplained", async () => {
    const client = api([post()], { state: vi.fn(async () => archive({ modelConfigured: false })) });

    render(<PostsScreen api={client} />);

    expect(await screen.findByText(/No model is configured/)).toBeInTheDocument();
  });

  it("says a read failed rather than emptying the screen", async () => {
    const client = api([], {
      recentPosts: vi.fn(async () => {
        throw new ArchiveError("unreachable", "social-data is not reachable");
      }),
    });

    render(<PostsScreen api={client} />);

    expect(await screen.findByText("social-data is not reachable")).toBeInTheDocument();
  });
});
