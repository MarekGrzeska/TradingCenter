import { describe, expect, it, vi } from "vitest";
import { createAgentActivityStore } from "./agentActivity";

/**
 * The channel that tells a tab a turn ended, so it can re-read state the chat wrote in a module the chat
 * store knows nothing about. Small enough that the tests are about the two ways this breaks.
 */

describe("the agent activity channel", () => {
  it("tells every listener that a turn ended", () => {
    const store = createAgentActivityStore();
    const teams = vi.fn();
    const schedules = vi.fn();
    store.subscribe(teams);
    store.subscribe(schedules);

    store.turnFinished();

    expect(teams).toHaveBeenCalledTimes(1);
    expect(schedules).toHaveBeenCalledTimes(1);
  });

  it("stops telling one that unsubscribed", () => {
    const store = createAgentActivityStore();
    const listener = vi.fn();
    const stop = store.subscribe(listener);

    stop();
    store.turnFinished();

    expect(listener).not.toHaveBeenCalled();
  });

  it("finishes the round even when a listener unsubscribes inside it", () => {
    // A tab unmounting on the same event is the ordinary case, not a corner one: the
    // operator switches away as the turn lands.
    const store = createAgentActivityStore();
    const second = vi.fn();
    const stop = store.subscribe(() => stop());
    store.subscribe(second);

    store.turnFinished();

    expect(second).toHaveBeenCalledTimes(1);
  });

  it("keeps one listener's failure to itself", () => {
    const store = createAgentActivityStore();
    const survivor = vi.fn();
    store.subscribe(() => {
      throw new Error("this tab is confused");
    });
    store.subscribe(survivor);

    expect(() => store.turnFinished()).not.toThrow();
    expect(survivor).toHaveBeenCalledTimes(1);
  });
});
