import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MarketDataError } from "../data/types";
import { TeamsView } from "./TeamsView";
import type { RunStreamEvent, TeamRun, TeamRunStep } from "./runs";
import type { TeamDefinition, TeamsApi, TeamSummary, TeamRevision } from "./teamsApi";

const MODELS = [
  {
    id: "cheap-one",
    displayName: "Mini",
    costRank: 1,
    inputRatePer1M: "0.1",
    outputRatePer1M: "0.4",
  },
  { id: "dear-one", displayName: "Luna", costRank: 2, inputRatePer1M: "1", outputRatePer1M: "6" },
];

const TEAM: TeamSummary = {
  id: 1,
  name: "Morning desk",
  description: "two roles",
  latestRevision: 2,
  createdAt: 1_760_000_000,
  updatedAt: 1_760_000_600,
};

const DEFINITION: TeamDefinition = {
  agents: [
    { key: "agent-1", role: "Scout", prompt: "look", guidance: "", modelId: "cheap-one", tools: [] },
    { key: "agent-2", role: "Judge", prompt: "weigh", guidance: "", modelId: "dear-one", tools: [] },
  ],
  dependencies: [{ from: "agent-1", to: "agent-2" }],
  limits: { runLimit: null, dailyLimit: null },
};

function revision(definition: TeamDefinition = DEFINITION): TeamRevision {
  return { id: 9, teamId: 1, version: 2, definition, createdAt: 1_760_000_600 };
}

/** Three roles, which is what the run scenarios in `terminal-teams` are written on: one
 *  finished, one working, one still waiting. */
const TRIO: TeamDefinition = {
  agents: [
    { key: "agent-1", role: "Scout", prompt: "look", guidance: "", modelId: "cheap-one", tools: [] },
    { key: "agent-2", role: "Judge", prompt: "weigh", guidance: "", modelId: "dear-one", tools: [] },
    { key: "agent-3", role: "Scribe", prompt: "write", guidance: "", modelId: "cheap-one", tools: [] },
  ],
  dependencies: [
    { from: "agent-1", to: "agent-2" },
    { from: "agent-2", to: "agent-3" },
  ],
  limits: { runLimit: null, dailyLimit: null },
};

const RUN: TeamRun = {
  id: 7,
  teamRevisionId: 9,
  status: "running",
  stoppedReason: null,
  startedAt: 1_760_000_700,
  finishedAt: null,
  createdAt: 1_760_000_700,
};

function step(id: number, agentKey: string, status: string, output: string | null = null): TeamRunStep {
  return {
    id,
    runId: RUN.id,
    agentKey,
    status,
    output,
    rounds: status === "pending" ? 0 : 1,
    startedAt: status === "pending" ? null : 1_760_000_700,
    finishedAt: status === "completed" || status === "failed" ? 1_760_000_800 : null,
  };
}

const MIDWAY: TeamRunStep[] = [
  step(1, "agent-1", "completed", "US100 is trending"),
  step(2, "agent-2", "running"),
  step(3, "agent-3", "pending"),
];

async function* streamOf(events: RunStreamEvent[]): AsyncGenerator<RunStreamEvent> {
  for (const event of events) yield event;
}

function fakeApi(overrides: Partial<TeamsApi> = {}): TeamsApi {
  return {
    listModels: vi.fn(async () => MODELS),
    listTools: vi.fn(async () => [{ name: "get_candles", description: "candles from the archive" }]),
    listTeams: vi.fn(async () => [TEAM]),
    createTeam: vi.fn(async () => TEAM),
    getTeam: vi.fn(async () => TEAM),
    latestRevision: vi.fn(async () => revision()),
    getRevision: vi.fn(async () => revision()),
    revisionById: vi.fn(async () => ({ ...revision(TRIO), id: RUN.teamRevisionId })),
    saveRevision: vi.fn(async () => revision()),
    archiveTeam: vi.fn(async () => {}),
    startRun: vi.fn(async () => RUN),
    listRuns: vi.fn(async () => [RUN]),
    getRun: vi.fn(async () => RUN),
    runSteps: vi.fn(async () => MIDWAY),
    runToolCalls: vi.fn(async () => []),
    cancelRun: vi.fn(async () => RUN),
    watchRun: vi.fn(async () => streamOf([{ kind: "snapshot", run: RUN, steps: MIDWAY }])),
    ...overrides,
  };
}

async function openTheTeam(api: TeamsApi) {
  render(<TeamsView api={api} />);
  await screen.findByText("Morning desk");
  await userEvent.click(screen.getByRole("button", { name: "Open" }));
  return screen.findByTestId("agent-node-Scout");
}

describe("the catalogue", () => {
  it("lists what the module published, without reading any definition", async () => {
    const api = fakeApi();
    render(<TeamsView api={api} />);

    expect(await screen.findByText("Morning desk")).toBeInTheDocument();
    expect(screen.getByText("two roles")).toBeInTheDocument();
    expect(api.latestRevision).not.toHaveBeenCalled();
  });

  it("says so plainly when there is nothing saved yet", async () => {
    render(<TeamsView api={fakeApi({ listTeams: vi.fn(async () => []) })} />);

    expect(await screen.findByText(/No teams yet/)).toBeInTheDocument();
  });
});

describe("the team on the canvas", () => {
  it("shows every agent with its role and the model it works on", async () => {
    // `terminal-teams`, "Przy każdym agencie MUST być widoczna jego rola i model" — the
    // model by the catalogue's display name, which is the only name the operator picked
    // it by.
    await openTheTeam(fakeApi());

    expect(within(screen.getByTestId("agent-node-Scout")).getByText("Mini")).toBeInTheDocument();
    expect(within(screen.getByTestId("agent-node-Judge")).getByText("Luna")).toBeInTheDocument();
  });

  it("adds an agent without leaving the view", async () => {
    await openTheTeam(fakeApi());

    await userEvent.click(screen.getByRole("button", { name: "Add agent" }));

    expect(await screen.findByTestId("agent-node-New role")).toBeInTheDocument();
  });
});

describe("the agent panel", () => {
  it("offers the models the module published and nothing else", async () => {
    // The requirement `terminal-teams` states twice: the picker is built from the
    // catalogue, and this terminal knows no model by name.
    await openTheTeam(fakeApi());

    const picker = await screen.findByLabelText("Model");
    expect([...(picker as HTMLSelectElement).options].map((option) => option.textContent)).toEqual([
      "Mini",
      "Luna",
    ]);
  });

  it("offers the tools the module announces, and saves the one that was ticked", async () => {
    const api = fakeApi();
    await openTheTeam(api);

    await userEvent.click(await screen.findByLabelText(/get_candles/));
    await userEvent.click(screen.getByRole("button", { name: "Save revision" }));

    await waitFor(() => expect(api.saveRevision).toHaveBeenCalled());
    const [, saved] = (api.saveRevision as ReturnType<typeof vi.fn>).mock.calls[0];
    expect((saved as TeamDefinition).agents[0].tools).toEqual(["get_candles"]);
  });

  it("says why the tool list is empty rather than showing an empty box", async () => {
    await openTheTeam(fakeApi({ listTools: vi.fn(async () => []) }));

    expect(await screen.findByText("the module announces no tools")).toBeInTheDocument();
  });

  it("removes a dependency from the agent it belongs to", async () => {
    const api = fakeApi();
    await openTheTeam(api);

    await userEvent.click(await screen.findByRole("button", { name: /Remove dependency/ }));
    await userEvent.click(screen.getByRole("button", { name: "Save revision" }));

    await waitFor(() => expect(api.saveRevision).toHaveBeenCalled());
    const [, saved] = (api.saveRevision as ReturnType<typeof vi.fn>).mock.calls[0];
    expect((saved as TeamDefinition).dependencies).toEqual([]);
  });
});

describe("starting a run", () => {
  async function startFrom(api: TeamsApi) {
    render(<TeamsView api={api} />);
    await screen.findByText("Morning desk");
    await userEvent.click(screen.getByRole("button", { name: "Run" }));
  }

  it("starts it from the catalogue and opens the run on the team's picture", async () => {
    // `terminal-teams`, "z każdej pozycji może otworzyć zespół albo uruchomić przebieg" —
    // and what comes back is the run, so the view that follows is the monitor.
    const api = fakeApi();
    await startFrom(api);

    await waitFor(() => expect(api.startRun).toHaveBeenCalledWith(TEAM.id, expect.anything()));
    expect(await screen.findByText("Run 7")).toBeInTheDocument();
    expect(await screen.findByTestId("agent-node-Scout")).toBeInTheDocument();
  });

  it("shows the module's refusal rather than a run that is not there", async () => {
    // A model withdrawn since the revision was saved, a tool no longer announced, the
    // team's daily budget spent — all one shape here: the module's own sentence.
    const api = fakeApi({
      startRun: vi.fn(async () => {
        throw new MarketDataError("refused", "the team spent 4.20 of its daily 4.00");
      }),
    });
    await startFrom(api);

    expect(await screen.findByText(/spent 4.20 of its daily 4.00/)).toBeInTheDocument();
    expect(screen.queryByText("Run 7")).not.toBeInTheDocument();
  });

  it("draws the revision the run works on, not the team's latest", async () => {
    // specs/teams-runs, "Przebieg odbywa się na rewizji, nie na zespole" — a revision
    // saved while the run works must not change the picture it is watched on.
    const api = fakeApi();
    await startFrom(api);

    await screen.findByTestId("agent-node-Scribe");
    expect(api.revisionById).toHaveBeenCalledWith(RUN.teamRevisionId, expect.anything());
    expect(api.latestRevision).not.toHaveBeenCalled();
  });
});

describe("watching a run", () => {
  async function watch(api: TeamsApi) {
    render(<TeamsView api={api} />);
    await screen.findByText("Morning desk");
    await userEvent.click(screen.getByRole("button", { name: "Runs" }));
    await userEvent.click(await screen.findByRole("button", { name: "Watch" }));
    return screen.findByTestId("agent-node-Scout");
  }

  it("says who has finished, who is working and who is still waiting", async () => {
    await watch(fakeApi());

    expect(within(screen.getByTestId("agent-node-Scout")).getByText("done")).toBeInTheDocument();
    expect(within(screen.getByTestId("agent-node-Judge")).getByText("working")).toBeInTheDocument();
    expect(within(screen.getByTestId("agent-node-Scribe")).getByText("waiting")).toBeInTheDocument();
  });

  it("follows the run as it moves, without asking again", async () => {
    const api = fakeApi({
      watchRun: vi.fn(async () =>
        streamOf([
          { kind: "snapshot", run: RUN, steps: MIDWAY },
          { kind: "stepFinished", agentKey: "agent-2", status: "completed", output: "buy" },
          { kind: "stepStarted", agentKey: "agent-3" },
        ]),
      ),
    });
    await watch(api);

    await waitFor(() =>
      expect(within(screen.getByTestId("agent-node-Scribe")).getByText("working")).toBeInTheDocument(),
    );
    expect(within(screen.getByTestId("agent-node-Judge")).getByText("done")).toBeInTheDocument();
    expect(api.runSteps).not.toHaveBeenCalled();
  });

  it("hands over what an agent produced and what it called", async () => {
    const api = fakeApi({
      runToolCalls: vi.fn(async () => [
        {
          runStepId: 1,
          roundIndex: 0,
          position: 0,
          toolName: "get_candles",
          outcome: "ok",
          durationMs: 42,
        },
      ]),
    });
    await watch(api);

    // `fireEvent`, not `userEvent`: a pointer press on the canvas wakes d3-zoom, which
    // reaches for `document` after jsdom has torn it down. The node listens for a click.
    fireEvent.click(screen.getByTestId("agent-node-Scout"));

    expect(await screen.findByText("US100 is trending")).toBeInTheDocument();
    expect(screen.getByText("get_candles")).toBeInTheDocument();
    expect(screen.getByText(/ok · 42 ms/)).toBeInTheDocument();
  });

  it("shows the run as it stands now when it is opened again, not as it was", async () => {
    // specs/teams-runs, "po ponownym otwarciu widać jego bieżący stan" — leaving the view
    // dropped the stream and nothing else, so the second connection opens on a snapshot
    // that has moved on.
    const finished = [
      step(1, "agent-1", "completed", "US100 is trending"),
      step(2, "agent-2", "completed", "buy"),
      step(3, "agent-3", "completed", "written up"),
    ];
    const watchRun = vi
      .fn()
      .mockResolvedValueOnce(streamOf([{ kind: "snapshot", run: RUN, steps: MIDWAY }]))
      .mockResolvedValueOnce(
        streamOf([
          {
            kind: "snapshot",
            run: { ...RUN, status: "completed", finishedAt: 1_760_001_000 },
            steps: finished,
          },
        ]),
      );
    const api = fakeApi({ watchRun });
    await watch(api);
    expect(within(screen.getByTestId("agent-node-Scribe")).getByText("waiting")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "← Catalogue" }));
    await userEvent.click(await screen.findByRole("button", { name: "Runs" }));
    await userEvent.click(await screen.findByRole("button", { name: "Watch" }));

    await waitFor(() =>
      expect(within(screen.getByTestId("agent-node-Scribe")).getByText("done")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("run-status")).toHaveTextContent("completed");
  });

  it("names the cost as the reason, and keeps what the agents had produced", async () => {
    // specs/teams-usage over the same view: a run stopped by its ceiling says so, and the
    // work already done stays readable.
    const stopped: TeamRun = {
      ...RUN,
      status: "failed",
      stoppedReason: "the run reached its cost limit of 2.00 (spent 2.01)",
      finishedAt: 1_760_000_900,
    };
    const api = fakeApi({
      watchRun: vi.fn(async () => streamOf([{ kind: "snapshot", run: stopped, steps: MIDWAY }])),
    });
    await watch(api);

    expect(await screen.findByText(/cost limit of 2.00/)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("agent-node-Scout"));
    expect(await screen.findByText("US100 is trending")).toBeInTheDocument();
    // Nothing left to stop, so nothing offering to.
    expect(screen.queryByRole("button", { name: "Stop" })).not.toBeInTheDocument();
  });

  it("asks the module to stop a run the operator interrupts", async () => {
    const api = fakeApi();
    await watch(api);

    await userEvent.click(screen.getByRole("button", { name: "Stop" }));

    await waitFor(() => expect(api.cancelRun).toHaveBeenCalledWith(RUN.id, expect.anything()));
  });
});

describe("a refused save", () => {
  it("shows the module's reason and opens the agent it names", async () => {
    // `terminal-teams`, "Zapis odrzucony przez moduł jest pokazany przy miejscu, którego
    // dotyczy" — the message names agent-2, so the panel is on agent-2 and its node is
    // marked, rather than a general "invalid" somewhere on the page.
    const refusal = new MarketDataError(
      "refused",
      "agent 'agent-2' names model 'gone', which is not in this module's model catalogue",
    );
    const api = fakeApi({
      saveRevision: vi.fn(async () => {
        throw refusal;
      }),
    });
    await openTheTeam(api);

    await userEvent.click(screen.getByRole("button", { name: "Add agent" }));
    await userEvent.click(screen.getByRole("button", { name: "Save revision" }));

    expect(await screen.findAllByText(refusal.message)).not.toHaveLength(0);
    expect(within(screen.getByTestId("agent-node-Judge")).getByText("refused")).toBeInTheDocument();
    expect((screen.getByLabelText("Role") as HTMLInputElement).value).toBe("Judge");
  });
});
