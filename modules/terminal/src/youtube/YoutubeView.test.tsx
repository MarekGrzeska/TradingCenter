import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { queryClient } from "../data/query";
import { MarketDataError } from "../data/types";
import { YoutubeView } from "./YoutubeView";
import type { ArchiveState, Channel, Film, FilmsPage, Reading, YoutubeApi } from "./youtubeApi";

/**
 * The tab from the operator's seat: that a film shows its score and what was said about each instrument, that an unread film
 * says where it is instead of a number, that the screen says why a list is thin, and that adding to the list refuses out loud.
 */

const READING: Reading = {
  summary: "Autor uważa, że złoto wzrośnie.",
  keyPoints: ["banki kupują złoto"],
  instruments: [{ name: "Gold", epic: "GOLD", sentiment: "bullish", conviction: 4, horizon: "swing" }],
  predictions: [{ instrument: "Gold", claim: "dochodzi do 3000", level: 3000, by: "2026-12-31" }],
  topics: ["złoto"],
  impactScore: 6,
  model: "sim",
  analysedAt: new Date("2026-09-27T10:05:00Z"),
  simulated: true,
};

function film(overrides: Partial<Film> = {}): Film {
  return {
    videoId: "v1",
    url: "https://www.youtube.com/watch?v=v1",
    title: "Złoto do 3000?",
    channelId: "UC1",
    channelTitle: "Sim Złoto PL",
    publishedAt: new Date("2026-09-27T08:30:00Z"),
    durationSeconds: 1500,
    liveStatus: "none",
    state: "quiet",
    skipReason: null,
    attempts: 0,
    nextAttemptAt: null,
    simulated: false,
    reading: READING,
    ...overrides,
  };
}

function state(overrides: Partial<ArchiveState> = {}): ArchiveState {
  return {
    simulating: false,
    modelConfigured: true,
    alertsConfigured: true,
    providers: [],
    waiting: {},
    stale: false,
    loopAgeSeconds: 10,
    ...overrides,
  };
}

const CHANNEL: Channel = {
  channelId: "UC1",
  title: "Sim Złoto PL",
  handle: "@simzloto",
  alertRule: "threshold",
  active: true,
  addedBy: "operator",
  lastDiscoveryAt: null,
};

function api(films: Film[], overrides: Partial<YoutubeApi> = {}): YoutubeApi {
  const page: FilmsPage = {
    films,
    windowFrom: new Date("2026-09-26T10:00:00Z"),
    windowTo: new Date("2026-09-27T10:00:00Z"),
  };
  return {
    recentFilms: vi.fn(async () => page),
    state: vi.fn(async () => state()),
    transcript: vi.fn(),
    channels: vi.fn(async () => ({ channels: [CHANNEL], ceiling: 100 })),
    followChannel: vi.fn(),
    setChannel: vi.fn(),
    unfollowChannel: vi.fn(async () => undefined),
    topics: vi.fn(async () => ({ topics: [], ceiling: 20 })),
    addTopic: vi.fn(),
    setTopic: vi.fn(),
    removeTopic: vi.fn(),
    analyse: vi.fn(),
    ...overrides,
  };
}

describe("YoutubeView", () => {
  it("shows a read film with its score and a direction per instrument, and its words a fold away", async () => {
    render(<YoutubeView api={api([film()])} />);

    expect(await screen.findByText("Złoto do 3000?")).toBeInTheDocument();
    expect(screen.getByText("6/10")).toBeInTheDocument();
    expect(screen.getByText(/Gold ▲ 4\/5/)).toBeInTheDocument();
    expect(screen.queryByText("banki kupują złoto")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /Złoto do 3000\?/ }));

    expect(screen.getByText("banki kupują złoto")).toBeInTheDocument();
    expect(screen.getByText(/dochodzi do 3000/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /obejrzyj na YouTube/ })).toHaveAttribute(
      "href",
      "https://www.youtube.com/watch?v=v1",
    );
  });

  it("shows no score at all on a film no model has read, and says where it is instead", async () => {
    render(<YoutubeView api={api([film({ reading: null, state: "no_transcript", attempts: 2 })])} />);

    expect(await screen.findByText(/brak napisów \(próba 2\)/)).toBeInTheDocument();
    // Not a zero and not a dash: both read as a judgement, and there is none.
    expect(screen.queryByText(/^\d+\/10$/)).not.toBeInTheDocument();
  });

  it("says, for as long as it is true, that the films come from a simulation", async () => {
    render(<YoutubeView api={api([film({ simulated: true })], { state: vi.fn(async () => state({ simulating: true })) })} />);

    expect(await screen.findByText(/SYMULACJA — filmy, transkrypcje lub odczyty pochodzą ze scenariusza/)).toBeInTheDocument();
    expect(screen.getByText("SYMULACJA")).toBeInTheDocument();
  });

  it("names a blocked provider and a missing model instead of letting a thin list speak for them", async () => {
    const client = api([], {
      state: vi.fn(async () =>
        state({
          modelConfigured: false,
          providers: [
            {
              role: "transcripts",
              name: "direct",
              unit: "requests",
              spentToday: 3,
              ceiling: 500,
              exhausted: false,
              blocked: true,
              blockedReason: "IpBlocked",
            },
          ],
        }),
      ),
    });

    render(<YoutubeView api={client} />);

    expect(await screen.findByText(/odmówił \(IpBlocked\)/)).toBeInTheDocument();
    expect(screen.getByText(/Model nie jest skonfigurowany/)).toBeInTheDocument();
    expect(screen.getByText("direct: 3/500 requests")).toBeInTheDocument();
  });

  it("says a workbench without the package has none, and is not an empty archive", async () => {
    const client = api([], {
      state: vi.fn(async () => {
        throw new MarketDataError("not-found", "Not Found");
      }),
    });

    render(<YoutubeView api={client} />);

    expect(await screen.findByText(/nie ma archiwum YouTube/)).toBeInTheDocument();
    expect(client.recentFilms).not.toHaveBeenCalled();
  });

  it("keeps the films on screen when a refresh fails", async () => {
    const recent = vi
      .fn()
      .mockResolvedValueOnce({ films: [film()], windowFrom: new Date(0), windowTo: new Date(0) })
      .mockRejectedValue(new MarketDataError("unreachable", "youtube-data is not reachable"));
    render(<YoutubeView api={api([], { recentFilms: recent })} />);
    expect(await screen.findByText("Złoto do 3000?")).toBeInTheDocument();

    await act(async () => {
      await queryClient.refetchQueries({ queryKey: ["youtube", "films"] });
    });

    expect(await screen.findByText(/youtube-data is not reachable/)).toBeInTheDocument();
    expect(screen.getByText("Złoto do 3000?")).toBeInTheDocument();
  });

  it("adds a channel from the tab, and keeps the module's reason in the dialog when it refuses", async () => {
    const followChannel = vi
      .fn()
      .mockRejectedValueOnce(new MarketDataError("refused", "the watch list holds 100 channels, which is its ceiling"));
    render(<YoutubeView api={api([], { followChannel })} />);

    await userEvent.click(await screen.findByRole("button", { name: "Kanały" }));
    await userEvent.click(await screen.findByRole("button", { name: "Obserwuj kanał" }));
    await userEvent.type(screen.getByPlaceholderText(/@nazwa/), "@zapelniony");
    await userEvent.click(screen.getByRole("button", { name: "Obserwuj" }));

    expect(await screen.findByText(/which is its ceiling/)).toBeInTheDocument();
    expect(followChannel).toHaveBeenCalledWith("@zapelniony", "threshold", expect.anything());
  });

  it("takes a channel off only after asking, and says its films stay", async () => {
    const client = api([]);
    render(<YoutubeView api={client} />);

    await userEvent.click(await screen.findByRole("button", { name: "Kanały" }));
    await userEvent.click(await screen.findByRole("button", { name: "Zdejmij" }));
    expect(screen.getByText(/zostają w archiwum/)).toBeInTheDocument();
    expect(client.unfollowChannel).not.toHaveBeenCalled();

    await userEvent.click(screen.getAllByRole("button", { name: "Zdejmij" }).at(-1)!);

    expect(client.unfollowChannel).toHaveBeenCalledWith("UC1", expect.anything());
  });
});
