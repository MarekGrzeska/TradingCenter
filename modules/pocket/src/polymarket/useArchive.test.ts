import { afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useArchive } from "./useArchive";
import type { PolymarketApi } from "./api";

function anApi(): PolymarketApi {
  return {
    listEvents: vi.fn(async () => []),
    listGroups: vi.fn(async () => []),
    changes: vi.fn(async () => []),
    trackEvent: vi.fn(),
    removeEvent: vi.fn(),
    renameGroup: vi.fn(),
    deleteGroup: vi.fn(),
    assignGroup: vi.fn(),
  } as PolymarketApi;
}

function setVisibility(state: DocumentVisibilityState) {
  vi.spyOn(document, "visibilityState", "get").mockReturnValue(state);
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("polling the archive", () => {
  it("asks nothing while the screen is hidden, and asks again the moment it is shown", async () => {
    vi.useFakeTimers();
    const api = anApi();
    renderHook(() => useArchive(api, 1_000));
    await act(async () => {});
    expect(api.listEvents).toHaveBeenCalledTimes(1);

    setVisibility("hidden");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });
    expect(api.listEvents).toHaveBeenCalledTimes(1);

    setVisibility("visible");
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(api.listEvents).toHaveBeenCalledTimes(2);
  });
});
