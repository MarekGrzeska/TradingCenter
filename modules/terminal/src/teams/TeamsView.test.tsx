import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { agentActivity } from "../agent/agentActivity";
import { MarketDataError } from "../data/types";
import { TeamsView } from "./TeamsView";
import type { RunStreamEvent, TeamRun, TeamRunStep, TeamTrade } from "./runs";
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
  trading: { maxOrderSize: null, ordersPerRun: null, ordersPerDay: null },
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
  trading: { maxOrderSize: null, ordersPerRun: null, ordersPerDay: null },
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

/** One order this run placed, settled unless a test says otherwise. */
function trade(over: Partial<TeamTrade> & { agentKey: string }): TeamTrade {
  return {
    id: 4,
    runId: RUN.id,
    toolName: "an order tool",
    symbol: "US100",
    direction: "BUY",
    size: "1.5",
    level: null,
    status: "settled",
    resultStatus: "FILLED",
    providerOrderId: "o-1",
    reference: null,
    createdAt: 1_760_000_800,
    settledAt: 1_760_000_801,
    ...over,
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
    listTools: vi.fn(async () => [
      { name: "get_candles", description: "candles from the archive", readOnly: true },
    ]),
    listTeams: vi.fn(async () => [TEAM]),
    createTeam: vi.fn(async () => TEAM),
    getTeam: vi.fn(async () => TEAM),
    latestRevision: vi.fn(async () => revision()),
    getRevision: vi.fn(async () => revision()),
    revisionById: vi.fn(async () => ({ ...revision(TRIO), id: RUN.teamRevisionId })),
    saveRevision: vi.fn(async () => revision()),
    archiveTeam: vi.fn(async () => {}),
    memory: vi.fn(async () => ({ entries: [], total: 0 })),
    deleteMemory: vi.fn(async () => {}),
    layout: vi.fn(async () => new Map<string, { x: number; y: number }>()),
    saveLayout: vi.fn(async () => {}),
    startRun: vi.fn(async () => RUN),
    listRuns: vi.fn(async () => [RUN]),
    getRun: vi.fn(async () => RUN),
    runSteps: vi.fn(async () => MIDWAY),
    runToolCalls: vi.fn(async () => []),
    runTrades: vi.fn(async () => []),
    cancelRun: vi.fn(async () => RUN),
    watchRun: vi.fn(async () => streamOf([{ kind: "snapshot", run: RUN, steps: MIDWAY }])),
    listSchedules: vi.fn(async () => []),
    createSchedule: vi.fn(async () => {
      throw new Error("not stubbed");
    }),
    updateSchedule: vi.fn(async () => {
      throw new Error("not stubbed");
    }),
    enableSchedule: vi.fn(async () => {
      throw new Error("not stubbed");
    }),
    disableSchedule: vi.fn(async () => {
      throw new Error("not stubbed");
    }),
    deleteSchedule: vi.fn(async () => undefined),
    deleteTrigger: vi.fn(async () => undefined),
    scheduleFires: vi.fn(async () => []),
    nextFires: vi.fn(async () => []),
    previewNextFires: vi.fn(async () => []),
    listTriggers: vi.fn(async () => []),
    createTrigger: vi.fn(async () => {
      throw new Error("not stubbed");
    }),
    updateTrigger: vi.fn(async () => {
      throw new Error("not stubbed");
    }),
    enableTrigger: vi.fn(async () => {
      throw new Error("not stubbed");
    }),
    disableTrigger: vi.fn(async () => {
      throw new Error("not stubbed");
    }),
    triggerFires: vi.fn(async () => []),
    ...overrides,
  };
}

async function openTheTeam(api: TeamsApi) {
  render(<TeamsView api={api} />);
  // A click on the row, which is what opening a team is since the `Open` button was dropped
  // — it was one of five on a row where opening is the common case.
  await userEvent.click(await screen.findByText("Morning desk"));
  return screen.findByTestId("agent-node-Scout");
}

  /** `fireEvent` because a pointer press wakes d3-zoom, which reaches for a `document` jsdom has torn down; by
   *  label because React Flow keeps a node hidden until measured, which never happens here. */
async function openAgentSettings(role: string) {
  fireEvent.click(
    within(screen.getByTestId(`agent-node-${role}`)).getByLabelText(`Settings for ${role}`),
  );
  return screen.findByRole("dialog");
}

async function closeAgentSettings() {
  await userEvent.click(screen.getByRole("button", { name: "Done" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
}


describe("the catalogue", () => {
  it("lists what the module published and opens a team on a click", async () => {
    // No `Open` button: it was one of five on a row where opening is the common case, and
    // the catalogue reads no definition to draw the list.
    const api = fakeApi();
    render(<TeamsView api={api} />);

    expect(await screen.findByText("Morning desk")).toBeInTheDocument();
    expect(screen.getByText("two roles")).toBeInTheDocument();
    expect(api.latestRevision).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Open" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByText("Morning desk"));

    expect(await screen.findByTestId("agent-node-Scout")).toBeInTheDocument();
  });

  it("says so plainly when there is nothing saved yet", async () => {
    render(<TeamsView api={fakeApi({ listTeams: vi.fn(async () => []) })} />);

    expect(await screen.findByText(/No teams yet/)).toBeInTheDocument();
  });

  it("shows a team the model created, without the operator reloading the page", async () => {
    // Reported from a running stack on 17 August 2026: `create_team` from the chat succeeded and the tab kept
    // showing the list it read on mount. Those writes never pass through this tab, so nothing invalidated it.
    const listTeams = vi
      .fn()
      .mockResolvedValueOnce([TEAM])
      .mockResolvedValue([TEAM, { ...TEAM, id: 2, name: "Built from the chat" }]);
    render(<TeamsView api={fakeApi({ listTeams })} />);
    await screen.findByText("Morning desk");
    expect(screen.queryByText("Built from the chat")).not.toBeInTheDocument();

    agentActivity.turnFinished();

    expect(await screen.findByText("Built from the chat")).toBeInTheDocument();
  });
});

describe("the team on the canvas", () => {
  it("shows every agent with its role and the model it works on", async () => {
    // `terminal-teams`, "Przy każdym agencie MUST być widoczna jego rola i model" — by the catalogue's display
    // name, which is the only name the operator picked it by.
    await openTheTeam(fakeApi());

    expect(within(screen.getByTestId("agent-node-Scout")).getByText("Mini")).toBeInTheDocument();
    expect(within(screen.getByTestId("agent-node-Judge")).getByText("Luna")).toBeInTheDocument();
  });

  it("adds an agent without leaving the view, and takes it back on Undo", async () => {
    await openTheTeam(fakeApi());

    await userEvent.click(screen.getByRole("button", { name: "Add agent" }));
    expect(await screen.findByTestId("agent-node-New role")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Undo" }));

    await waitFor(() =>
      expect(screen.queryByTestId("agent-node-New role")).not.toBeInTheDocument(),
    );
    expect(screen.getByTestId("agent-node-Scout")).toBeInTheDocument();
  });
});

describe("the agent settings dialog", () => {
  it("opens from the gear on the agent's own box, and closes again", async () => {
    // The narrow column this replaced was always on screen; a dialog has to be asked for,
    // so the asking is what the operator has to be able to find and undo.
    await openTheTeam(fakeApi());

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await openAgentSettings("Judge");

    expect(screen.getByRole("dialog")).toHaveAccessibleName("Agent: Judge");
    expect((screen.getByLabelText("Role") as HTMLInputElement).value).toBe("Judge");
    // The picker is built from the catalogue: this terminal knows no model by name.
    const picker = await screen.findByLabelText("Model");
    expect([...(picker as HTMLSelectElement).options].map((option) => option.textContent)).toEqual([
      "Mini",
      "Luna",
    ]);

    await closeAgentSettings();
  });

  it("offers the tools the module announces, and saves the one that was ticked", async () => {
    const api = fakeApi();
    await openTheTeam(api);
    await openAgentSettings("Scout");

    await userEvent.click(await screen.findByLabelText(/get_candles/));
    await closeAgentSettings();
    await userEvent.click(screen.getByRole("button", { name: "Save revision" }));

    await waitFor(() => expect(api.saveRevision).toHaveBeenCalled());
    const [, saved] = (api.saveRevision as ReturnType<typeof vi.fn>).mock.calls[0];
    expect((saved as TeamDefinition).agents[0].tools).toEqual(["get_candles"]);
  });

  it("says why the tool list is empty rather than showing an empty box", async () => {
    await openTheTeam(fakeApi({ listTools: vi.fn(async () => []) }));
    await openAgentSettings("Scout");

    expect(await screen.findByText("the module announces no tools")).toBeInTheDocument();
  });

  it("shows a refused save's reason and opens the agent it names", async () => {
    // `terminal-teams`, "Zapis odrzucony przez moduł jest pokazany przy miejscu, którego dotyczy": the message
    // names agent-2, so its settings open and its node is marked, not a general "invalid" on the page.
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
    expect(await screen.findByRole("dialog")).toHaveAccessibleName("Agent: Judge");
  });
});

describe("the trading limits", () => {
  it("sets them in the same view the team is composed in", async () => {
    // specs/terminal-teams, "Granice handlowe ustawia się w tym samym widoku co resztę
    // zespołu" — on the team rather than on any one agent, and needing no button to reach.
    const api = fakeApi();
    await openTheTeam(api);

    await userEvent.type(await screen.findByLabelText("Largest order size"), "1.5");
    await userEvent.type(screen.getByLabelText("Orders per run"), "2");
    await userEvent.click(screen.getByRole("button", { name: "Save revision" }));

    await waitFor(() => expect(api.saveRevision).toHaveBeenCalled());
    const [, saved] = (api.saveRevision as ReturnType<typeof vi.fn>).mock.calls[0];
    expect((saved as TeamDefinition).trading).toEqual({
      maxOrderSize: "1.5",
      ordersPerRun: 2,
      ordersPerDay: null,
    });
  });

  it("marks the tools that move the account, and says when nobody annotated one", async () => {
    // specs/terminal-teams, "narzędzia zmieniające stan rachunku są odróżnione od czytających" — read off the
    // server's own annotation, with `null` kept as a third value rather than promoted to "reads only".
    const api = fakeApi({
      listTools: vi.fn(async () => [
        { name: "get_candles", description: "candles", readOnly: true },
        { name: "place_order", description: "an order", readOnly: false },
        { name: "who_knows", description: "nobody said", readOnly: null },
      ]),
    });
    await openTheTeam(api);
    await openAgentSettings("Scout");

    const writes = (await screen.findByText("place_order")).closest("label");
    expect(within(writes as HTMLElement).getByText("moves the account")).toBeInTheDocument();
    const reads = screen.getByText("get_candles").closest("label");
    expect(within(reads as HTMLElement).queryByText("moves the account")).not.toBeInTheDocument();
    const unknown = screen.getByText("who_knows").closest("label");
    expect(within(unknown as HTMLElement).getByText("unannotated")).toBeInTheDocument();
  });
});

describe("starting a run", () => {
  it("starts it from the catalogue and opens the run on the revision it works on", async () => {
    // specs/teams-runs, "Przebieg odbywa się na rewizji, nie na zespole" — a revision saved
    // while the run works must not change the picture it is watched on.
    const api = fakeApi();
    render(<TeamsView api={api} />);
    await screen.findByText("Morning desk");

    await userEvent.click(screen.getByRole("button", { name: "Run" }));

    await waitFor(() => expect(api.startRun).toHaveBeenCalledWith(TEAM.id, expect.anything()));
    expect(await screen.findByTestId("run-status")).toBeInTheDocument();
    await screen.findByTestId("agent-node-Scribe");
    expect(api.revisionById).toHaveBeenCalledWith(RUN.teamRevisionId, expect.anything());
    expect(api.latestRevision).not.toHaveBeenCalled();
  });

  it("shows the module's refusal rather than a run that is not there", async () => {
    // A model withdrawn since the revision was saved, a tool no longer announced, the
    // team's daily budget spent — all one shape here: the module's own sentence.
    const api = fakeApi({
      startRun: vi.fn(async () => {
        throw new MarketDataError("refused", "the team spent 4.20 of its daily 4.00");
      }),
    });
    render(<TeamsView api={api} />);
    await screen.findByText("Morning desk");

    await userEvent.click(screen.getByRole("button", { name: "Run" }));

    expect(await screen.findByText(/spent 4.20 of its daily 4.00/)).toBeInTheDocument();
    expect(screen.queryByText("Run 7")).not.toBeInTheDocument();
  });

  it("asks the question naming the revision before a run started from the runs view", async () => {
    // A run costs tokens and, for a team with the order tools, places demo orders.
    const started = { ...RUN, id: 9, status: "pending" };
    const api = fakeApi({ listRuns: vi.fn(async () => []), startRun: vi.fn(async () => started) });
    render(<TeamsView api={api} />);
    await screen.findByText("Morning desk");
    await userEvent.click(screen.getByRole("button", { name: "Runs" }));

    await userEvent.click(await screen.findByRole("button", { name: /Run now/ }));
    expect(await screen.findByRole("dialog", { name: "Run now" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/the team's latest/)).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Start the run" }));

    await waitFor(() => expect(api.startRun).toHaveBeenCalledWith(1, expect.anything()));
    await waitFor(() => expect(api.watchRun).toHaveBeenCalledWith(9, expect.anything()));
  });
});

describe("watching a run", () => {
  async function watch(api: TeamsApi) {
    render(<TeamsView api={api} />);
    await screen.findByText("Morning desk");
    // One click: `Runs` is a view of its own and it opens on the newest run rather than
    // unfolding a list that then needs a second click on `Watch`.
    await userEvent.click(screen.getByRole("button", { name: "Runs" }));
    return screen.findByTestId("agent-node-Scout");
  }

  it("says who has finished, who is working and who is still waiting, and follows the run", async () => {
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

    expect(within(screen.getByTestId("agent-node-Scout")).getByText("done")).toBeInTheDocument();
    await waitFor(() =>
      expect(within(screen.getByTestId("agent-node-Scribe")).getByText("working")).toBeInTheDocument(),
    );
    expect(within(screen.getByTestId("agent-node-Judge")).getByText("done")).toBeInTheDocument();
    // Followed off the stream, never re-read.
    expect(api.runSteps).not.toHaveBeenCalled();
  });

  it("says the connection was lost when the stream ends on a run that is still working", async () => {
    // The module closes the stream itself only once the run is over, so a body that ends
    // while an agent is working is a dropped connection — and one that says nothing looks
    // exactly like an agent thinking. What is on screen stays: the run is still running,
    // it is this view that stopped following it.
    await watch(fakeApi());

    expect(await screen.findByText(/the connection to the run was lost/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Watch again" })).toBeInTheDocument();
    expect(within(screen.getByTestId("agent-node-Scout")).getByText("done")).toBeInTheDocument();
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
    expect(screen.getByText("Cost limit")).toBeInTheDocument();
    // `fireEvent`, not `userEvent`: a pointer press on the canvas wakes d3-zoom, which
    // reaches for `document` after jsdom has torn it down. The node listens for a click.
    fireEvent.click(screen.getByTestId("agent-node-Scout"));
    expect(await screen.findByText("US100 is trending")).toBeInTheDocument();
    // Nothing left to stop, so nothing offering to.
    expect(screen.queryByRole("button", { name: "Stop" })).not.toBeInTheDocument();
  });

  it("shows an order beside the agent that placed it", async () => {
    // specs/terminal-teams, "Złożone zlecenia widać przy agencie, który je złożył" — with
    // the symbol, the direction, the size and what came of it.
    const api = fakeApi({ runTrades: vi.fn(async () => [trade({ agentKey: "agent-1" })]) });
    await watch(api);

    fireEvent.click(screen.getByTestId("agent-node-Scout"));

    const orders = (await screen.findByText("Orders")).closest("section") as HTMLElement;
    expect(within(orders).getByText("US100")).toBeInTheDocument();
    expect(within(orders).getByText("BUY")).toBeInTheDocument();
    expect(within(orders).getByText(/1\.5/)).toBeInTheDocument();
    expect(within(orders).getByText("FILLED")).toBeInTheDocument();
  });

  it("narrows the outputs window to one agent and keeps its calls collapsed until asked", async () => {
    const api = fakeApi({
      runToolCalls: vi.fn(async () => [
        {
          runStepId: 1,
          roundIndex: 0,
          position: 0,
          toolName: "get_candles",
          outcome: "ok",
          durationMs: 42,
          detail: { arguments: { symbol: "US100" }, resultText: "12 candles" },
        },
      ]),
    });
    await watch(api);
    await userEvent.click(await screen.findByRole("button", { name: /^Outputs/ }));
    const dialog = await screen.findByRole("dialog");

    await userEvent.click(within(dialog).getByRole("button", { name: /Scout/ }));

    expect(within(dialog).getByText("US100 is trending")).toBeInTheDocument();
    expect(within(dialog).getByText(/ok · 42 ms/)).toBeInTheDocument();
    expect(within(dialog).queryByText("12 candles")).not.toBeInTheDocument();

    await userEvent.click(within(dialog).getByRole("button", { name: /Expand get_candles/ }));

    expect(within(dialog).getByText(/"symbol": ?"US100"/)).toBeInTheDocument();
    expect(within(dialog).getByText("12 candles")).toBeInTheDocument();
  });

  it("says a call watched live has not been read rather than showing it empty", async () => {
    // The stream frame carries the name and the outcome and no body — see `runs.ts`. An
    // empty result here would read as a tool that answered nothing.
    const api = fakeApi({
      watchRun: vi.fn(async () =>
        streamOf([
          { kind: "snapshot", run: RUN, steps: MIDWAY },
          {
            kind: "toolCall",
            call: {
              agentKey: "agent-1",
              roundIndex: 0,
              position: 0,
              toolName: "get_balance",
              outcome: "ok",
              durationMs: 9,
            },
          },
        ]),
      ),
    });
    await watch(api);
    await userEvent.click(await screen.findByRole("button", { name: /^Outputs/ }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /Scout/ }));
    await userEvent.click(within(dialog).getByRole("button", { name: /Expand get_balance/ }));

    expect(within(dialog).getByText(/have not been read yet/)).toBeInTheDocument();
    expect(within(dialog).queryByText("arguments")).not.toBeInTheDocument();
  });
});
