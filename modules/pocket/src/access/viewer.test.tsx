import { render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { NewsScreen } from "../news/NewsScreen";
import type { NewsApi, NewsItem } from "../news/api";
import { PolymarketScreen } from "../polymarket/PolymarketScreen";
import type { PolymarketApi } from "../polymarket/api";
import { anEvent } from "../test/builders";
import type { AccessApi } from "./accessApi";
import { useRole } from "./useRole";

const answering = (roles: string[]): AccessApi => ({ me: vi.fn(async () => ({ roles, person: "p" })) });

function polymarket(): PolymarketApi {
  return {
    listEvents: vi.fn(async () => [anEvent({ title: "Rate cut" })]),
    listGroups: vi.fn(async () => [{ id: 1, name: "Macro", eventCount: 1 }]),
    changes: vi.fn(async () => []),
    trackEvent: vi.fn(),
    removeEvent: vi.fn(),
    renameGroup: vi.fn(),
    deleteGroup: vi.fn(),
    assignGroup: vi.fn(),
  } as unknown as PolymarketApi;
}

describe("a viewer's screens", () => {
  it("offer the observation list and nothing that writes to it", async () => {
    render(<PolymarketScreen api={polymarket()} readOnly />);
    await userEvent.click(await screen.findByRole("button", { expanded: false }));

    expect(await screen.findByRole("link", { name: /polymarket\.com/i })).toBeInTheDocument();
    for (const name of ["Track event", "Groups", "Remove", "Move to group"]) {
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }
  });

  it("show the headlines without a Keep button", async () => {
    const item = {
      source: "reuters",
      externalId: "1",
      publisher: "Reuters",
      title: "Oil jumps",
      summary: "",
      content: "",
      url: null,
      publishedAt: new Date(),
      firstSeenAt: new Date(),
      delayMinSeconds: 1,
      delayMaxSeconds: 2,
      delayUnmeasured: null,
      keptAt: null,
      expiresAt: null,
    } as NewsItem;
    const api: NewsApi = {
      getNews: vi.fn(async () => ({ items: [item], count: 1, truncated: false })),
      getNewsSources: vi.fn(async () => []),
      setKept: vi.fn(),
    } as unknown as NewsApi;

    render(<NewsScreen api={api} readOnly />);

    expect(await screen.findByText("Oil jumps")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Keep" })).not.toBeInTheDocument();
  });
});

describe("useRole", () => {
  it.each([
    [["admin"], "admin"],
    [["viewer"], "viewer"],
    [[], "none"],
  ] as const)("reads %j as %s", async (roles, expected) => {
    const { result } = renderHook(() => useRole(answering([...roles]), "signed-in"));
    await waitFor(() => expect(result.current).toBe(expected));
  });

  it("falls back to the narrower screen when it cannot ask, and to the admin's one locally", async () => {
    const down: AccessApi = {
      me: vi.fn(async () => {
        throw new Error("down");
      }),
    };
    const failed = renderHook(() => useRole(down, "signed-in"));
    await waitFor(() => expect(failed.result.current).toBe("viewer"));

    expect(renderHook(() => useRole(down, "unconfigured")).result.current).toBe("admin");
  });
});
