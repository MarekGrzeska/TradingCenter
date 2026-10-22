import { describe, expect, it } from "vitest";
import { duration, stateLabel, usageLine, warnings } from "./present";
import type { ArchiveState, Film, ProviderState } from "./youtubeApi";

/** The sentences the screen says, as text: what a film without a reading says about itself, and why a list may be thin. */

function film(overrides: Partial<Film> = {}): Film {
  return {
    videoId: "v1",
    url: "https://www.youtube.com/watch?v=v1",
    title: "A film",
    channelId: "UC1",
    channelTitle: "A Channel",
    publishedAt: new Date("2026-09-27T08:00:00Z"),
    durationSeconds: 600,
    liveStatus: "none",
    state: "discovered",
    skipReason: null,
    attempts: 0,
    nextAttemptAt: null,
    simulated: false,
    promptId: 1,
    reading: null,
    ...overrides,
  };
}

function provider(overrides: Partial<ProviderState> = {}): ProviderState {
  return {
    role: "transcripts",
    name: "direct",
    unit: "requests",
    spentToday: 12,
    ceiling: 500,
    exhausted: false,
    blocked: false,
    blockedReason: null,
    ...overrides,
  };
}

function state(overrides: Partial<ArchiveState> = {}): ArchiveState {
  return {
    simulating: false,
    modelConfigured: true,
    channelsFiltered: 0,
    alertsConfigured: true,
    providers: [provider()],
    waiting: {},
    stale: false,
    loopAgeSeconds: 30,
    ...overrides,
  };
}

describe("stateLabel", () => {
  it("says where an unread film is, and why, in the words of its state", () => {
    expect(stateLabel(film())).toBe("czeka na transkrypcję");
    expect(stateLabel(film({ state: "no_transcript", attempts: 2 }))).toContain("próba 2");
    expect(stateLabel(film({ state: "gave_up", attempts: 4 }))).toBe("porzucony: brak napisów po 4 próbach");
    expect(stateLabel(film({ state: "skipped", skipReason: "shorter than the 60-second floor" }))).toContain("floor");
    expect(stateLabel(film({ state: "filtered_out", skipReason: "To sesja Q&A." }))).toBe(
      "pominięty przez filtr kanału: To sesja Q&A.",
    );
  });

  it("says a stream is being waited for before it says anything about captions", () => {
    expect(stateLabel(film({ liveStatus: "live", state: "discovered" }))).toContain("transmisja");
  });
});

describe("duration", () => {
  it("says nothing where the source could not say, and never a zero", () => {
    expect(duration(null)).toBeNull();
    expect(duration(20)).toBe("1 min");
    expect(duration(3720)).toBe("1 h 02 min");
  });
});

describe("warnings", () => {
  it("is empty when the archive is simply working, so the list speaks for itself", () => {
    expect(warnings(state())).toEqual([]);
  });

  it("names a blocked provider as a fact about us and not about the films", () => {
    const [note] = warnings(state({ providers: [provider({ blocked: true, blockedReason: "IpBlocked" })] }));

    expect(note).toContain("odmówił");
    expect(note).toContain("IpBlocked");
    expect(note).toContain("zostaje w kolejce");
  });

  it("stays quiet about a refused captions provider while another one delivers the words", () => {
    const refused = provider({ name: "direct", blocked: true, blockedReason: "RequestBlocked" });
    const delivering = provider({ name: "gemini" });

    expect(warnings(state({ providers: [refused, delivering] }))).toEqual([]);
    expect(warnings(state({ providers: [refused, { ...delivering, blocked: true }] }))).toHaveLength(2);
  });

  it("says a spent day comes back at midnight UTC, and which midnight", () => {
    const [note] = warnings(
      state({ providers: [provider({ exhausted: true, spentToday: 500 })] }),
      new Date("2026-09-27T13:00:00Z"),
    );

    expect(note).toContain("północy UTC");
    expect(note).toContain("2026-09-28 00:00 UTC");
  });

  it("says the films of a filtered channel wait while no model can judge them, and only then", () => {
    const waiting = (overrides: Partial<ArchiveState>) =>
      warnings(state({ channelsFiltered: 2, ...overrides })).filter((note) => note.includes("Kanały z filtrem"));

    expect(waiting({ modelConfigured: false })).toHaveLength(1);
    expect(waiting({ providers: [provider({ role: "analyser", exhausted: true })] })).toHaveLength(1);
    expect(waiting({})).toEqual([]);
    expect(warnings(state({ modelConfigured: false })).filter((note) => note.includes("Kanały z filtrem"))).toEqual([]);
  });

  it("says a stopped loop and a missing model, each once", () => {
    const notes = warnings(state({ stale: true, modelConfigured: false, loopAgeSeconds: 7200 }));

    expect(notes).toHaveLength(2);
    expect(notes[0]).toContain("120 min");
    expect(notes[1]).toContain("Model nie jest skonfigurowany");
  });
});

describe("usageLine", () => {
  it("is the day's spend in the provider's own unit", () => {
    expect(usageLine(provider())).toBe("direct: 12/500 requests");
  });
});
