import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { queryClient } from "../data/query";
import { MarketDataError } from "../data/types";
import { YoutubeView } from "./YoutubeView";
import type {
  ArchiveState,
  Candidate,
  Channel,
  Film,
  FilmsPage,
  Prompt,
  Reading,
  Topic,
  TopicRun,
  YoutubeApi,
} from "./youtubeApi";

/**
 * The tab from the operator's seat: that a film shows its score and summary and, opened, each reading under its prompt, that an unread film
 * says where it is instead of a number, that the screen says why a list is thin, and that adding to the list refuses out loud.
 */

const READING: Reading = {
  promptId: 1,
  promptName: "Rynkowy",
  promptVersion: 1,
  summary: "Autor uważa, że złoto wzrośnie.",
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
    promptId: 1,
    reading: READING,
    ...overrides,
  };
}

function state(overrides: Partial<ArchiveState> = {}): ArchiveState {
  return {
    simulating: false,
    modelConfigured: true,
    channelsFiltered: 0,
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
  active: true,
  addedBy: "operator",
  promptId: 1,
  lastDiscoveryAt: null,
  filter: null,
};

function run(overrides: Partial<TopicRun> = {}): TopicRun {
  return {
    id: 1,
    topicId: 7,
    phrase: "gold outlook",
    ranAt: new Date("2026-09-27T10:00:00Z"),
    outcome: "found",
    results: 5,
    known: 2,
    outOfBounds: 0,
    proposed: 2,
    rejected: 1,
    unscreened: 0,
    unscreenedReason: null,
    error: null,
    ...overrides,
  };
}

const TOPIC: Topic = {
  id: 7,
  phrase: "gold outlook",
  language: "",
  intervalMinutes: 60,
  maxVideosPerRun: 5,
  active: true,
  addedBy: "operator",
  lastRunAt: new Date("2026-09-27T10:00:00Z"),
  lastRun: null,
};

const CANDIDATE: Candidate = {
  videoId: "c1",
  url: "https://www.youtube.com/watch?v=c1",
  title: "Nowy autor o złocie",
  channelId: "UC9",
  channelTitle: "Nieznany Kanał",
  topic: "gold",
  publishedAt: new Date("2026-10-21T08:00:00Z"),
  durationSeconds: 1200,
  foundAt: new Date("2026-10-22T06:00:00Z"),
  verdict: "proposed",
  reason: "Konkretne poziomy i uzasadnienie, bez clickbaitu.",
  decision: null,
  simulated: false,
};

const SEEDED: Prompt = {
  id: 1,
  name: "Rynkowy",
  seeded: true,
  version: 1,
  body: "Streszcz film dla tradera.",
  createdAt: new Date("2026-10-22T09:00:00Z"),
  updatedAt: new Date("2026-10-22T09:00:00Z"),
  channels: ["Sim Złoto PL"],
};
const TECHNICAL: Prompt = { ...SEEDED, id: 2, name: "Technical", seeded: false, body: "Levels only.", channels: [] };

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
    topicRuns: vi.fn(async () => ({ runs: [], retentionDays: 30 })),
    addTopic: vi.fn(),
    setTopic: vi.fn(),
    removeTopic: vi.fn(),
    candidates: vi.fn(async () => [CANDIDATE]),
    followCandidateChannel: vi.fn(async () => ({ channel: CHANNEL, created: true })),
    analyseCandidate: vi.fn(),
    dismissCandidate: vi.fn(async () => undefined),
    ignoreCandidateChannel: vi.fn(async () => undefined),
    ignoredChannels: vi.fn(async () => []),
    unignoreChannel: vi.fn(async () => undefined),
    analyse: vi.fn(),
    film: vi.fn(async () => ({
      film: film(),
      readings: [{ ...READING, text: "## Główne tezy\n- banki kupują złoto\n\n## Prognozy\n- Gold: dochodzi do 3000" }],
    })),
    readAgain: vi.fn(async () => undefined),
    prompts: vi.fn(async () => ({ prompts: [SEEDED, TECHNICAL], maxChars: 8000, ceiling: 50 })),
    createPrompt: vi.fn(),
    updatePrompt: vi.fn(),
    deletePrompt: vi.fn(async () => undefined),
    settings: vi.fn(),
    updateSettings: vi.fn(),
    ...overrides,
  };
}

describe("YoutubeView", () => {
  it("shows a read film with its score and summary, and the reading under its prompt a fold away", async () => {
    render(<YoutubeView api={api([film()])} />);

    expect(await screen.findByText("Złoto do 3000?")).toBeInTheDocument();
    expect(screen.getByText("6/10")).toBeInTheDocument();
    expect(screen.getByText("Autor uważa, że złoto wzrośnie.")).toBeInTheDocument();
    expect(screen.queryByText("banki kupują złoto")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /Złoto do 3000\?/ }));

    expect(await screen.findByText("banki kupują złoto")).toBeInTheDocument();
    expect(screen.getByText(/dochodzi do 3000/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Rynkowy/ })).toBeInTheDocument();
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
    expect(followChannel).toHaveBeenCalledWith("@zapelniony", null, null, expect.anything());
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

  it("orders another prompt's reading of a film and says it was accepted", async () => {
    const client = api([film()]);
    render(<YoutubeView api={client} />);

    await userEvent.click(await screen.findByRole("button", { name: /Złoto do 3000\?/ }));
    await userEvent.selectOptions(await screen.findByRole("combobox", { name: /Odczytaj innym promptem/ }), "Technical");
    await userEvent.click(screen.getByRole("button", { name: "Zamów" }));

    expect(client.readAgain).toHaveBeenCalledWith("v1", 2, expect.anything());
    expect(await screen.findByText(/Przyjęte — odczyt powstaje w tle/)).toBeInTheDocument();
  });

  it("follows a channel by the prompt chosen in the dialog", async () => {
    const followChannel = vi.fn(async () => ({ channel: CHANNEL, created: true }));
    render(<YoutubeView api={api([], { followChannel })} />);

    await userEvent.click(await screen.findByRole("button", { name: "Kanały" }));
    await userEvent.click(await screen.findByRole("button", { name: "Obserwuj kanał" }));
    await userEvent.type(screen.getByPlaceholderText(/@nazwa/), "@nowy");
    await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Prompt" }), "Technical");
    await userEvent.click(screen.getByRole("button", { name: "Obserwuj" }));

    expect(followChannel).toHaveBeenCalledWith("@nowy", 2, null, expect.anything());
  });

  it("follows a channel with the filter typed in the dialog, and without one when the field is left empty", async () => {
    const followChannel = vi.fn(async () => ({ channel: CHANNEL, created: true }));
    render(<YoutubeView api={api([], { followChannel })} />);

    await userEvent.click(await screen.findByRole("button", { name: "Kanały" }));
    await userEvent.click(await screen.findByRole("button", { name: "Obserwuj kanał" }));
    await userEvent.type(screen.getByPlaceholderText(/@nazwa/), "@makro");
    await userEvent.type(screen.getByPlaceholderText(/tylko analizy makro/), "  tylko analizy makro ");
    await userEvent.click(screen.getByRole("button", { name: "Obserwuj" }));

    expect(followChannel).toHaveBeenCalledWith("@makro", null, "tylko analizy makro", expect.anything());
  });

  it("says a filter typed for a channel already followed was not set, and where it is changed", async () => {
    const followChannel = vi.fn(async () => ({ channel: CHANNEL, created: false }));
    render(<YoutubeView api={api([], { followChannel })} />);

    await userEvent.click(await screen.findByRole("button", { name: "Kanały" }));
    await userEvent.click(await screen.findByRole("button", { name: "Obserwuj kanał" }));
    await userEvent.type(screen.getByPlaceholderText(/@nazwa/), "@simzloto");
    await userEvent.type(screen.getByPlaceholderText(/tylko analizy makro/), "bez Q&A");
    await userEvent.click(screen.getByRole("button", { name: "Obserwuj" }));

    expect(await screen.findByText(/Wpisany filtr nie został ustawiony/)).toBeInTheDocument();
  });

  it("sets a channel's filter from its row, takes it off when emptied, and keeps the module's refusal in the dialog", async () => {
    const setChannel = vi
      .fn()
      .mockResolvedValueOnce(CHANNEL)
      .mockRejectedValueOnce(new MarketDataError("refused", "a filter is 1 to 1000 characters"))
      .mockResolvedValueOnce(CHANNEL);
    const filtered = { ...CHANNEL, filter: "tylko analizy makro" };
    render(<YoutubeView api={api([], { setChannel, channels: vi.fn(async () => ({ channels: [filtered], ceiling: 100 })) })} />);

    await userEvent.click(await screen.findByRole("button", { name: "Kanały" }));
    expect(await screen.findByText("tylko analizy makro")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Filtr…" }));
    const field = screen.getByRole("textbox", { name: /Filtr — które filmy/ });
    await userEvent.clear(field);
    await userEvent.type(field, "bez Q&A");
    await userEvent.click(screen.getByRole("button", { name: "Zapisz" }));
    expect(setChannel).toHaveBeenLastCalledWith("UC1", { filter: "bez Q&A" }, expect.anything());

    await userEvent.click(await screen.findByRole("button", { name: "Filtr…" }));
    await userEvent.click(screen.getByRole("button", { name: "Zapisz" }));
    expect(await screen.findByText(/1 to 1000 characters/)).toBeInTheDocument();

    await userEvent.clear(screen.getByRole("textbox", { name: /Filtr — które filmy/ }));
    await userEvent.click(screen.getByRole("button", { name: "Zapisz" }));
    expect(setChannel).toHaveBeenLastCalledWith("UC1", { filter: null }, expect.anything());
  });

  it("lists what a filter turned away only when asked, with the reason, and analyses it anyway", async () => {
    const turned = film({ state: "filtered_out", reading: null, skipReason: "To sesja Q&A z widzami." });
    const recentFilms = vi.fn(async (_hours: number, _signal: AbortSignal, state?: string) => ({
      films: state === "filtered_out" ? [turned] : [],
      windowFrom: new Date("2026-09-26T10:00:00Z"),
      windowTo: new Date("2026-09-27T10:00:00Z"),
    }));
    const client = api([], { recentFilms, analyse: vi.fn(async () => ({ videoId: "v1", title: "Złoto do 3000?", created: false })) });
    render(<YoutubeView api={client} />);

    expect(await screen.findByText(/Brak filmów z ostatnich/)).toBeInTheDocument();
    expect(screen.queryByText("Złoto do 3000?")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Pominięte przez filtr" }));
    expect(await screen.findByText(/pominięty przez filtr kanału: To sesja Q&A z widzami\./)).toBeInTheDocument();
    expect(recentFilms).toHaveBeenLastCalledWith(24, expect.anything(), "filtered_out");

    await userEvent.click(screen.getByRole("button", { name: /Złoto do 3000\?/ }));
    await userEvent.click(await screen.findByRole("button", { name: "Analizuj mimo to" }));

    expect(client.analyse).toHaveBeenCalledWith("v1", null, expect.anything());
    expect(await screen.findByText(/Przyjęte — film jest transkrybowany/)).toBeInTheDocument();
  });

  it("keeps the prompts a section away inside the tab, not in a tab of their own", async () => {
    render(<YoutubeView api={api([])} />);

    await userEvent.click(await screen.findByRole("button", { name: "Prompty" }));

    expect(await screen.findByText("Technical")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Nowy prompt" })).toBeInTheDocument();
  });

  it("lists the searches newest first, each with its report, and says why one that failed did", async () => {
    const topicRuns = vi.fn(async () => ({
      runs: [
        run({ id: 3, outcome: "failed", results: 0, known: 0, proposed: 0, rejected: 0, error: "YouTube nie odpowiada" }),
        run({ id: 2, outcome: "nothing_new", results: 3, known: 3, proposed: 0, rejected: 0 }),
        run({ id: 1, unscreened: 2, proposed: 0, rejected: 0, unscreenedReason: "no_model" }),
      ],
      retentionDays: 30,
    }));
    render(<YoutubeView api={api([], { topicRuns, topics: vi.fn(async () => ({ topics: [TOPIC], ceiling: 20 })) })} />);

    await userEvent.click(await screen.findByRole("button", { name: "Kandydaci" }));
    await userEvent.click(await screen.findByRole("button", { name: "Historia wyszukiwań" }));

    expect(await screen.findByText("YouTube nie odpowiada")).toBeInTheDocument();
    expect(screen.getByText("nieudany")).toBeInTheDocument();
    expect(screen.getByText(/3 wyników · 3 znanych/)).toBeInTheDocument();
    expect(screen.getByText(/2 bez przesiewu \(brak modelu\)/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ostatnio znalezione" })).not.toBeInTheDocument();
  });

  it("narrows the history to one topic, and says when no search has happened yet", async () => {
    const topicRuns = vi.fn(async () => ({ runs: [], retentionDays: 30 }));
    render(<YoutubeView api={api([], { topicRuns, topics: vi.fn(async () => ({ topics: [TOPIC], ceiling: 20 })) })} />);

    await userEvent.click(await screen.findByRole("button", { name: "Kandydaci" }));
    await userEvent.click(await screen.findByRole("button", { name: "Historia wyszukiwań" }));
    expect(await screen.findByText(/Nie było jeszcze żadnego przebiegu/)).toBeInTheDocument();

    await userEvent.selectOptions(await screen.findByRole("combobox", { name: /Temat/ }), "gold outlook");

    expect(topicRuns).toHaveBeenLastCalledWith({ topicId: 7 }, expect.anything());
  });

  it("narrows the history to days, both included, says when none had a search, and clears them", async () => {
    const topicRuns = vi.fn(async () => ({ runs: [], retentionDays: 30 }));
    render(<YoutubeView api={api([], { topicRuns })} />);

    await userEvent.click(await screen.findByRole("button", { name: "Kandydaci" }));
    await userEvent.click(await screen.findByRole("button", { name: "Historia wyszukiwań" }));
    fireEvent.change(await screen.findByLabelText("Od"), { target: { value: "2026-10-22" } });
    fireEvent.change(screen.getByLabelText("Do"), { target: { value: "2026-10-24" } });

    expect(await screen.findByText(/W wybranych dniach nie było przebiegów/)).toBeInTheDocument();
    expect(topicRuns).toHaveBeenLastCalledWith(
      { topicId: undefined, since: new Date(2026, 9, 22), until: new Date(2026, 9, 25) },
      expect.anything(),
    );

    await userEvent.click(screen.getByRole("button", { name: "Wyczyść dni" }));

    expect(await screen.findByText(/Nie było jeszcze żadnego przebiegu/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Wyczyść dni" })).not.toBeInTheDocument();
  });

  it("says a range that ends before it starts is empty, and does not send it", async () => {
    const topicRuns = vi.fn(async () => ({ runs: [], retentionDays: 30 }));
    render(<YoutubeView api={api([], { topicRuns })} />);

    await userEvent.click(await screen.findByRole("button", { name: "Kandydaci" }));
    await userEvent.click(await screen.findByRole("button", { name: "Historia wyszukiwań" }));
    fireEvent.change(await screen.findByLabelText("Do"), { target: { value: "2026-10-20" } });
    const calls = topicRuns.mock.calls.length;
    fireEvent.change(screen.getByLabelText("Od"), { target: { value: "2026-10-24" } });

    expect(await screen.findByText(/Dzień początkowy jest po końcowym/)).toBeInTheDocument();
    expect(topicRuns.mock.calls.length).toBe(calls);
  });

  it("shows how each topic's last search ended, in the topics' own tab", async () => {
    const lastRun = run({ outcome: "failed", error: "limit źródła wyczerpany" });
    render(<YoutubeView api={api([], { topics: vi.fn(async () => ({ topics: [{ ...TOPIC, lastRun }], ceiling: 20 })) })} />);

    await userEvent.click(await screen.findByRole("button", { name: "Tematy" }));

    expect(await screen.findByText(/ostatni przebieg: nieudany — limit źródła wyczerpany/)).toBeInTheDocument();
  });

  it("lists candidates with a link to the film and the model's reason, and asks again in the other order", async () => {
    const client = api([]);
    render(<YoutubeView api={client} />);

    await userEvent.click(await screen.findByRole("button", { name: "Kandydaci" }));

    expect(await screen.findByRole("link", { name: "Nowy autor o złocie" })).toHaveAttribute(
      "href",
      "https://www.youtube.com/watch?v=c1",
    );
    expect(screen.getByText(/Konkretne poziomy/)).toBeInTheDocument();
    expect(client.candidates).toHaveBeenLastCalledWith({ view: "open", sort: "found" }, expect.anything());

    await userEvent.click(screen.getByRole("button", { name: "Ostatnio opublikowane" }));

    await vi.waitFor(() =>
      expect(client.candidates).toHaveBeenLastCalledWith({ view: "open", sort: "published" }, expect.anything()),
    );
  });

  it("follows a candidate's channel by the prompt chosen, and keeps the reason in the dialog when the list is full", async () => {
    const followCandidateChannel = vi
      .fn()
      .mockRejectedValueOnce(new MarketDataError("refused", "the watch list holds 100 channels, which is its ceiling"))
      .mockResolvedValueOnce({ channel: CHANNEL, created: true });
    render(<YoutubeView api={api([], { followCandidateChannel })} />);

    await userEvent.click(await screen.findByRole("button", { name: "Kandydaci" }));
    await userEvent.click(await screen.findByRole("button", { name: "Obserwuj kanał" }));
    await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Prompt" }), "Technical");
    await userEvent.click(screen.getByRole("button", { name: "Obserwuj" }));

    expect(await screen.findByText(/which is its ceiling/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Nowy autor o złocie" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Obserwuj" }));

    await vi.waitFor(() => expect(followCandidateChannel).toHaveBeenCalledTimes(2));
    expect(followCandidateChannel).toHaveBeenLastCalledWith("c1", 2, expect.anything());
  });

  it("dismisses a candidate at once and ignores a channel only after asking", async () => {
    const client = api([]);
    render(<YoutubeView api={client} />);

    await userEvent.click(await screen.findByRole("button", { name: "Kandydaci" }));
    await userEvent.click(await screen.findByRole("button", { name: "Odrzuć" }));
    expect(client.dismissCandidate).toHaveBeenCalledWith("c1", expect.anything());

    await userEvent.click(screen.getByRole("button", { name: "Ignoruj kanał" }));
    expect(client.ignoreCandidateChannel).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Ignoruj" }));

    await vi.waitFor(() => expect(client.ignoreCandidateChannel).toHaveBeenCalledWith("c1", expect.anything()));
  });
});
