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
    scheduleFires: vi.fn(async () => []),
    nextFires: vi.fn(async () => []),
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

/** The node React Flow positions, which is the parent of what `AgentNode` renders — the
 *  `transform` is where a place ends up, so it is where a test can read one. */
function nodeElement(testId: string): HTMLElement {
  const node = screen.getByTestId(testId).closest(".react-flow__node");
  if (!(node instanceof HTMLElement)) throw new Error(`${testId} is not on the canvas`);
  return node;
}

async function openTheTeam(api: TeamsApi) {
  render(<TeamsView api={api} />);
  // A click on the row, which is what opening a team is since the `Open` button was dropped
  // — it was one of five on a row where opening is the common case.
  await userEvent.click(await screen.findByText("Morning desk"));
  return screen.findByTestId("agent-node-Scout");
}

/** An agent's fields live in a dialog now, opened by the gear on its own box.
 *
 *  `fireEvent` for the same reason the node clicks below use it: a pointer press on the
 *  canvas wakes d3-zoom, which reaches for a `document` jsdom has already torn down. And
 *  by label rather than by role, because React Flow keeps a node `visibility: hidden`
 *  until it has measured it — which never happens in jsdom, so nothing on this canvas is
 *  in the accessibility tree a `ByRole` query walks. */
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

describe("the catalogue's own affordances", () => {
  it("opens a team on a click, and offers no Open button to do it with", async () => {
    render(<TeamsView api={fakeApi()} />);

    await userEvent.click(await screen.findByText("Morning desk"));

    expect(await screen.findByTestId("agent-node-Scout")).toBeInTheDocument();
  });

  it("leaves a click that landed on one of the row's buttons to that button", async () => {
    // The row is the way in and it carries four buttons: `Schedules` must open schedules,
    // not the editor underneath the pointer.
    render(<TeamsView api={fakeApi()} />);
    await screen.findByText("Morning desk");

    await userEvent.click(screen.getByRole("button", { name: "Schedules" }));

    expect(await screen.findByRole("button", { name: "New schedule" })).toBeInTheDocument();
    expect(screen.queryByTestId("agent-node-Scout")).not.toBeInTheDocument();
  });

  it("says so, because a click on a row is not visible the way a button was", async () => {
    render(<TeamsView api={fakeApi()} />);

    expect(await screen.findByText(/Click a team to open it/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open" })).not.toBeInTheDocument();
    // And on the row itself, which is what a pointer lands on. Its visibility is the
    // stylesheet's job — that it is there to be revealed is this file's.
    const row = (await screen.findByText("Morning desk")).closest("li") as HTMLElement;
    expect(within(row).getByText("click to open")).toBeInTheDocument();
    expect(row).toHaveAttribute("title", "Click to open");
  });

  it("opens it from the keyboard too, which a double-click cannot", async () => {
    render(<TeamsView api={fakeApi()} />);
    const row = (await screen.findByText("Morning desk")).closest("li") as HTMLElement;

    row.focus();
    await userEvent.keyboard("{Enter}");

    expect(await screen.findByTestId("agent-node-Scout")).toBeInTheDocument();
  });
});

describe("a team's runs, as a view of their own", () => {
  it("goes to the runs and opens the newest, rather than unfolding a list to click twice", async () => {
    const older = { ...RUN, id: 5, status: "completed", finishedAt: 1_760_000_900 };
    const api = fakeApi({ listRuns: vi.fn(async () => [RUN, older]) });
    render(<TeamsView api={api} />);
    await screen.findByText("Morning desk");

    await userEvent.click(screen.getByRole("button", { name: "Runs" }));

    // Every run of the team is on screen, and the newest is the one drawn underneath.
    expect(await screen.findByRole("button", { name: /Run 7/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Run 5/ })).toBeInTheDocument();
    expect(await screen.findByTestId("agent-node-Scout")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Watch" })).not.toBeInTheDocument();
  });

  it("switches the picture to another run without leaving the list", async () => {
    // The whole reason this stopped being a drawer inside the catalogue: comparing two runs
    // used to mean walking back out and in again.
    const older = { ...RUN, id: 5, status: "completed", finishedAt: 1_760_000_900 };
    const api = fakeApi({
      listRuns: vi.fn(async () => [RUN, older]),
      getRun: vi.fn(async (id: number) => (id === 5 ? older : RUN)),
      watchRun: vi.fn(async (id: number) =>
        streamOf([
          {
            kind: "snapshot",
            run: id === 5 ? older : RUN,
            steps: id === 5 ? [step(1, "agent-1", "failed")] : MIDWAY,
          },
        ]),
      ),
    });
    render(<TeamsView api={api} />);
    await screen.findByText("Morning desk");
    await userEvent.click(screen.getByRole("button", { name: "Runs" }));
    await screen.findByTestId("agent-node-Scout");

    await userEvent.click(screen.getByRole("button", { name: /Run 5/ }));

    await waitFor(() => expect(api.watchRun).toHaveBeenCalledWith(5, expect.anything()));
    await waitFor(() =>
      expect(within(screen.getByTestId("agent-node-Scout")).getByText("failed")).toBeInTheDocument(),
    );
    // Still the list: both runs are pickable from where the operator already is.
    expect(screen.getByRole("button", { name: /Run 7/ })).toBeInTheDocument();
  });

  it("says there is nothing rather than showing an empty canvas", async () => {
    render(<TeamsView api={fakeApi({ listRuns: vi.fn(async () => []) })} />);
    await screen.findByText("Morning desk");

    await userEvent.click(screen.getByRole("button", { name: "Runs" }));

    expect(await screen.findByText(/No runs yet/)).toBeInTheDocument();
    expect(screen.getByText(/Pick a run/)).toBeInTheDocument();
  });
});

describe("the loop between editing and reading a run", () => {
  it("shows the team's last runs while it is being edited", async () => {
    const older = { ...RUN, id: 5, status: "completed", finishedAt: 1_760_000_900 };
    await openTheTeam(fakeApi({ listRuns: vi.fn(async () => [RUN, older]) }));

    const strip = (await screen.findByText("Runs")).closest("div") as HTMLElement;
    expect(within(strip).getByRole("button", { name: /^7/ })).toBeInTheDocument();
    expect(within(strip).getByRole("button", { name: /^5/ })).toBeInTheDocument();
  });

  it("opens one of them straight from the editor, without the catalogue in between", async () => {
    const api = fakeApi({ listRuns: vi.fn(async () => [RUN]) });
    await openTheTeam(api);

    const strip = (await screen.findByText("Runs")).closest("div") as HTMLElement;
    await userEvent.click(within(strip).getByRole("button", { name: /^7/ }));

    await waitFor(() => expect(api.watchRun).toHaveBeenCalledWith(RUN.id, expect.anything()));
    expect(await screen.findByTestId("run-status")).toBeInTheDocument();
    // And on the team the editor was open on, named without looking it up again.
    expect(screen.getByText(/Morning desk/)).toBeInTheDocument();
  });

  it("switches back to editing from the runs view", async () => {
    await openTheTeam(fakeApi({ listRuns: vi.fn(async () => [RUN]) }));
    await userEvent.click(await screen.findByRole("button", { name: "Runs →" }));
    await screen.findByTestId("run-status");

    await userEvent.click(screen.getByRole("button", { name: "← Edit team" }));

    // The canvas is editable again: the gear is back on the boxes.
    expect(await screen.findByLabelText("Settings for Scout")).toBeInTheDocument();
  });

  it("offers no runs for a team that does not exist yet", async () => {
    render(<TeamsView api={fakeApi()} />);
    await userEvent.click(await screen.findByRole("button", { name: "New team" }));

    expect(await screen.findByRole("button", { name: "Create team" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Runs →" })).not.toBeInTheDocument();
  });
});

describe("what the chat changed", () => {
  it("shows a team the model created, without the operator reloading the page", async () => {
    // Reported from a running stack on 17 August 2026: `create_team` from the chat
    // succeeded, the team was in the module, and the tab kept showing the list it read on
    // mount. `teams-mcp`'s writes never pass through this tab, so nothing invalidated it.
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

  it("does not re-read the catalogue on its own between turns", async () => {
    // The refresh is tied to a turn ending, not to a timer: a tab that polls is a tab
    // that spends requests on nothing for as long as it is open.
    const api = fakeApi();
    render(<TeamsView api={api} />);
    await screen.findByText("Morning desk");

    expect(api.listTeams).toHaveBeenCalledTimes(1);
  });

  it("leaves a team open on the canvas alone", async () => {
    // A draft is what the operator is typing into. Re-reading it here would replace their
    // unsaved edit with a revision they did not ask for — the catalogue is a read, an open
    // editor is not.
    const api = fakeApi();
    await openTheTeam(api);
    await openAgentSettings("Scout");
    await userEvent.type(screen.getByLabelText("Role"), "ing");
    expect(await screen.findByTestId("agent-node-Scouting")).toBeInTheDocument();
    const readsBefore = (api.latestRevision as ReturnType<typeof vi.fn>).mock.calls.length;

    agentActivity.turnFinished();

    // Still the operator's text, and the editor asked the module nothing.
    expect((screen.getByLabelText("Role") as HTMLInputElement).value).toBe("Scouting");
    expect((api.latestRevision as ReturnType<typeof vi.fn>).mock.calls).toHaveLength(
      readsBefore,
    );
  });
});

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

  it("puts an agent where the operator left it, and calls that no change at all", async () => {
    // specs/terminal-teams, "Rozmieszczenie agentów jest wyborem operatora" — the layout
    // is read beside the revision and is not part of it, so a remembered place must not
    // read as something waiting to be saved.
    const api = fakeApi({
      layout: vi.fn(async () => new Map([["agent-1", { x: 640, y: 80 }]])),
    });
    await openTheTeam(api);

    await waitFor(() =>
      expect(nodeElement("agent-node-Scout").style.transform).toContain("translate(640px,80px)"),
    );
    expect(api.layout).toHaveBeenCalledWith(1, expect.anything());
    expect(screen.queryByText("unsaved changes")).not.toBeInTheDocument();
  });

  it("places an agent the layout does not name from its dependencies", async () => {
    // The judge was added after the last drag: it gets the column `layout()` computes for
    // it rather than the corner, and the scout stays where it was put.
    const api = fakeApi({
      layout: vi.fn(async () => new Map([["agent-1", { x: 640, y: 80 }]])),
    });
    await openTheTeam(api);

    await waitFor(() =>
      expect(nodeElement("agent-node-Scout").style.transform).toContain("translate(640px,80px)"),
    );
    expect(nodeElement("agent-node-Judge").style.transform).toContain("translate(280px,0px)");
  });

  it("adds an agent without leaving the view", async () => {
    await openTheTeam(fakeApi());

    await userEvent.click(screen.getByRole("button", { name: "Add agent" }));

    expect(await screen.findByTestId("agent-node-New role")).toBeInTheDocument();
  });
});

describe("taking the last change back", () => {
  it("undoes an agent that was just added", async () => {
    await openTheTeam(fakeApi());

    await userEvent.click(screen.getByRole("button", { name: "Add agent" }));
    expect(await screen.findByTestId("agent-node-New role")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Undo" }));

    await waitFor(() =>
      expect(screen.queryByTestId("agent-node-New role")).not.toBeInTheDocument(),
    );
    expect(screen.getByTestId("agent-node-Scout")).toBeInTheDocument();
  });

  it("undoes a removed dependency, which is what puts the line back", async () => {
    await openTheTeam(fakeApi());
    await openAgentSettings("Scout");

    await userEvent.click(await screen.findByRole("button", { name: /Remove dependency/ }));
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /Remove dependency/ })).not.toBeInTheDocument(),
    );
    await closeAgentSettings();
    expect(screen.getByText("unsaved changes")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Undo" }));

    await openAgentSettings("Scout");
    expect(await screen.findByRole("button", { name: /Remove dependency/ })).toBeInTheDocument();
    // And back to nothing to save: the draft is the saved revision again, which is the
    // whole of what "take it back" means here.
    await waitFor(() => expect(screen.queryByText("unsaved changes")).not.toBeInTheDocument());
  });

  it("answers to Ctrl+Z as well as to the button", async () => {
    await openTheTeam(fakeApi());
    await userEvent.click(screen.getByRole("button", { name: "Add agent" }));
    await screen.findByTestId("agent-node-New role");

    fireEvent.keyDown(document, { key: "z", ctrlKey: true });

    await waitFor(() =>
      expect(screen.queryByTestId("agent-node-New role")).not.toBeInTheDocument(),
    );
  });

  it("leaves the shortcut to the field that has the text in it", async () => {
    // Inside a textarea the browser's own undo is the better one, and taking it away to
    // revert the whole agent instead would be the worse trade.
    await openTheTeam(fakeApi());
    await userEvent.click(screen.getByRole("button", { name: "Add agent" }));
    await openAgentSettings("Scout");
    const prompt = await screen.findByLabelText("Prompt");

    fireEvent.keyDown(prompt, { key: "z", ctrlKey: true });

    expect(screen.getByTestId("agent-node-New role")).toBeInTheDocument();
  });

  it("has nothing to take back on a team just opened", async () => {
    await openTheTeam(fakeApi());

    expect(screen.getByRole("button", { name: "Undo" })).toBeDisabled();
  });

  it("collapses a burst of typing into one step", async () => {
    // `edit` runs per keystroke; one undo gives back what was there before the typing
    // started rather than the word minus its last letter.
    await openTheTeam(fakeApi());
    await openAgentSettings("Scout");

    await userEvent.type(await screen.findByLabelText("Role"), "ing");
    expect(await screen.findByTestId("agent-node-Scouting")).toBeInTheDocument();

    await closeAgentSettings();
    await userEvent.click(screen.getByRole("button", { name: "Undo" }));

    expect(await screen.findByTestId("agent-node-Scout")).toBeInTheDocument();
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

    await closeAgentSettings();
  });

  it("closes on Escape without touching the draft", async () => {
    await openTheTeam(fakeApi());
    await openAgentSettings("Scout");

    await userEvent.keyboard("{Escape}");

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.queryByText("unsaved changes")).not.toBeInTheDocument();
  });

  it("offers no gear on a run being watched", async () => {
    // That revision is saved and immutable — a gear opening fields nothing will keep is a
    // gear that lies.
    render(<TeamsView api={fakeApi()} />);
    await screen.findByText("Morning desk");
    await userEvent.click(screen.getByRole("button", { name: "Runs" }));
    await screen.findByTestId("agent-node-Scout");

    expect(screen.queryByLabelText(/^Settings for/)).not.toBeInTheDocument();
  });

  it("offers the models the module published and nothing else", async () => {
    // The requirement `terminal-teams` states twice: the picker is built from the
    // catalogue, and this terminal knows no model by name.
    await openTheTeam(fakeApi());
    await openAgentSettings("Scout");

    const picker = await screen.findByLabelText("Model");
    expect([...(picker as HTMLSelectElement).options].map((option) => option.textContent)).toEqual([
      "Mini",
      "Luna",
    ]);
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

  it("makes an agent wait for another one without dragging anything", async () => {
    // The canvas keeps its handles; this is the same edge drawn from the dialog, and it is
    // the path a test can walk — jsdom has no layout, so a drag between two handles is not
    // something this suite can prove either way.
    const loose: TeamDefinition = { ...DEFINITION, dependencies: [] };
    const api = fakeApi({ latestRevision: vi.fn(async () => revision(loose)) });
    await openTheTeam(api);
    await openAgentSettings("Judge");

    await userEvent.selectOptions(await screen.findByLabelText("Waits for"), "agent-1");
    await userEvent.click(screen.getByRole("button", { name: "Add" }));
    await closeAgentSettings();
    await userEvent.click(screen.getByRole("button", { name: "Save revision" }));

    await waitFor(() => expect(api.saveRevision).toHaveBeenCalled());
    const [, saved] = (api.saveRevision as ReturnType<typeof vi.fn>).mock.calls[0];
    expect((saved as TeamDefinition).dependencies).toEqual([{ from: "agent-1", to: "agent-2" }]);
  });

  it("offers no one to wait for when it already waits for everyone it could", async () => {
    // The default team is two agents with one edge between them, so the judge's only
    // candidate is the scout it already waits for — and itself, which is never a candidate.
    await openTheTeam(fakeApi());
    await openAgentSettings("Judge");

    expect(await screen.findByText(/waits for Scout/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Waits for")).not.toBeInTheDocument();
  });

  it("removes a dependency from the agent it belongs to", async () => {
    const api = fakeApi();
    await openTheTeam(api);
    await openAgentSettings("Scout");

    await userEvent.click(await screen.findByRole("button", { name: /Remove dependency/ }));
    await closeAgentSettings();
    await userEvent.click(screen.getByRole("button", { name: "Save revision" }));

    await waitFor(() => expect(api.saveRevision).toHaveBeenCalled());
    const [, saved] = (api.saveRevision as ReturnType<typeof vi.fn>).mock.calls[0];
    expect((saved as TeamDefinition).dependencies).toEqual([]);
  });
});

describe("the trading limits", () => {
  it("sets them in the same view the team is composed in", async () => {
    // specs/terminal-teams, "Granice handlowe ustawia się w tym samym widoku co resztę
    // zespołu" — the panel beside the canvas, on the team rather than on any one agent, and
    // since the agents moved into a dialog it is the whole of that panel and needs no button
    // to reach.
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

  it("saves an agent given a write tool and no limit at all, because none is required", async () => {
    // The reversed decision this change carries (specs/teams-trading, "Każda granica
    // handlowa daje się wyłączyć, a moduł żadnej nie narzuca"): an empty limit is the
    // operator's choice, not an omission for the terminal to nag about or hold a save on.
    const api = fakeApi({
      listTools: vi.fn(async () => [
        { name: "place_order", description: "an order", readOnly: false },
      ]),
    });
    await openTheTeam(api);
    await openAgentSettings("Scout");

    await userEvent.click(await screen.findByLabelText(/place_order/));
    await closeAgentSettings();
    await userEvent.click(screen.getByRole("button", { name: "Save revision" }));

    await waitFor(() => expect(api.saveRevision).toHaveBeenCalled());
    const [, saved] = (api.saveRevision as ReturnType<typeof vi.fn>).mock.calls[0];
    expect((saved as TeamDefinition).trading).toEqual({
      maxOrderSize: null,
      ordersPerRun: null,
      ordersPerDay: null,
    });
  });

  it("takes a limit back like any other change", async () => {
    await openTheTeam(fakeApi());

    await userEvent.type(await screen.findByLabelText("Orders per day"), "5");
    expect(screen.getByText("unsaved changes")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Undo" }));

    await waitFor(() =>
      expect((screen.getByLabelText("Orders per day") as HTMLInputElement).value).toBe(""),
    );
  });

  it("marks the tools that move the account, and says when nobody annotated one", async () => {
    // specs/terminal-teams, "narzędzia zmieniające stan rachunku są odróżnione od
    // czytających" — read off the server's own annotation, with `null` kept as a third
    // value rather than promoted to "reads only".
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
    // The run is named twice now, and both are the point: once in the team's run list and
    // once on the monitor underneath it.
    expect(await screen.findAllByText(/Run 7/)).not.toHaveLength(0);
    expect(await screen.findByTestId("run-status")).toBeInTheDocument();
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
    // One click now: `Runs` is a view of its own and it opens on the newest run rather
    // than unfolding a list that then needs a second click on `Watch`.
    await userEvent.click(screen.getByRole("button", { name: "Runs" }));
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

    await waitFor(() =>
      expect(within(screen.getByTestId("agent-node-Scribe")).getByText("done")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("run-status")).toHaveTextContent("completed");
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

  it("says nothing about a lost connection when the run finished on the stream", async () => {
    const api = fakeApi({
      watchRun: vi.fn(async () =>
        streamOf([
          { kind: "snapshot", run: RUN, steps: MIDWAY },
          { kind: "runFinished", status: "completed", stoppedReason: null },
        ]),
      ),
    });
    await watch(api);

    await waitFor(() => expect(screen.getByTestId("run-status")).toHaveTextContent("completed"));
    expect(screen.queryByText(/the connection to the run was lost/)).not.toBeInTheDocument();
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
    fireEvent.click(screen.getByTestId("agent-node-Scout"));
    expect(await screen.findByText("US100 is trending")).toBeInTheDocument();
    // Nothing left to stop, so nothing offering to.
    expect(screen.queryByRole("button", { name: "Stop" })).not.toBeInTheDocument();
  });

  it("shows an order beside the agent that placed it", async () => {
    // specs/terminal-teams, "Złożone zlecenia widać przy agencie, który je złożył" — with
    // the symbol, the direction, the size and what came of it, and beside the agent
    // rather than inside a list of tool calls nobody reads for this.
    const api = fakeApi({ runTrades: vi.fn(async () => [trade({ agentKey: "agent-1" })]) });
    await watch(api);

    fireEvent.click(screen.getByTestId("agent-node-Scout"));

    const orders = (await screen.findByText("Orders")).closest("section") as HTMLElement;
    expect(within(orders).getByText("US100")).toBeInTheDocument();
    expect(within(orders).getByText("BUY")).toBeInTheDocument();
    expect(within(orders).getByText(/1\.5/)).toBeInTheDocument();
    expect(within(orders).getByText("FILLED")).toBeInTheDocument();
  });

  it("shows an order of unknown outcome as unknown rather than dropping it", async () => {
    const api = fakeApi({
      runTrades: vi.fn(async () => [
        trade({ agentKey: "agent-1", status: "unknown", resultStatus: null }),
      ]),
    });
    await watch(api);

    fireEvent.click(screen.getByTestId("agent-node-Scout"));

    expect(await screen.findByText("outcome unknown")).toBeInTheDocument();
  });

  it("names the order limit as the reason, apart from the cost, and lists what was placed", async () => {
    // specs/terminal-teams, "Zatrzymanie z powodu granicy zleceń jest pokazane jako
    // takie" — the module's sentence, headed by which ceiling it was, and the orders the
    // team did place beneath it.
    const stopped: TeamRun = {
      ...RUN,
      status: "failed",
      stoppedReason: "the run's order limit was reached: 2 of 2 allowed placed.",
      finishedAt: 1_760_000_900,
    };
    const api = fakeApi({
      watchRun: vi.fn(async () => streamOf([{ kind: "snapshot", run: stopped, steps: MIDWAY }])),
      runTrades: vi.fn(async () => [trade({ agentKey: "agent-1" })]),
    });
    await watch(api);

    expect(await screen.findByText("Order limit")).toBeInTheDocument();
    expect(screen.queryByText("Cost limit")).not.toBeInTheDocument();
    expect(await screen.findByText("Orders placed (1)")).toBeInTheDocument();
  });

  it("reads every agent's output in a window of its own, formatted as the model wrote it", async () => {
    // The 20rem column is shaped for "is anything stuck"; reading what the agents said is
    // a different job, and the raw `**` was the other half of the complaint.
    const api = fakeApi({
      runSteps: vi.fn(async () => [
        step(1, "agent-1", "completed", "**US100** is trending\n\n- higher highs\n- volume flat"),
        step(2, "agent-2", "completed", "I would wait"),
        step(3, "agent-3", "pending"),
      ]),
      watchRun: vi.fn(async () =>
        streamOf([
          {
            kind: "snapshot",
            run: { ...RUN, status: "completed", finishedAt: 1_760_001_000 },
            steps: [
              step(1, "agent-1", "completed", "**US100** is trending\n\n- higher highs\n- volume flat"),
              step(2, "agent-2", "completed", "I would wait"),
              step(3, "agent-3", "pending"),
            ],
          },
        ]),
      ),
    });
    await watch(api);

    await userEvent.click(await screen.findByRole("button", { name: "Outputs (2)" }));

    const dialog = await screen.findByRole("dialog");
    // Every agent at once, which is how a finished run is read — in order, seams included.
    expect(within(dialog).getByText("is trending")).toBeInTheDocument();
    expect(within(dialog).getByText("I would wait")).toBeInTheDocument();
    // Markdown, not the punctuation the model typed: bold is an element and the list is a
    // list (`MessageBody`, the same renderer the chat uses).
    expect(within(dialog).getByText("US100").tagName).toBe("STRONG");
    expect(within(dialog).getAllByRole("listitem")).toHaveLength(2);
    expect(within(dialog).queryByText(/\*\*/)).not.toBeInTheDocument();
  });

  it("narrows to one agent, with what it called beside what it wrote", async () => {
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
    await userEvent.click(await screen.findByRole("button", { name: /^Outputs/ }));
    const dialog = await screen.findByRole("dialog");

    await userEvent.click(within(dialog).getByRole("button", { name: /Scout/ }));

    expect(within(dialog).getByText("US100 is trending")).toBeInTheDocument();
    expect(within(dialog).getByText("get_candles")).toBeInTheDocument();
    expect(within(dialog).getByText(/ok · 42 ms/)).toBeInTheDocument();
  });

  it("closes the outputs window on Escape", async () => {
    await watch(fakeApi());
    await userEvent.click(await screen.findByRole("button", { name: /^Outputs/ }));
    await screen.findByRole("dialog");

    await userEvent.keyboard("{Escape}");

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
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
    // dotyczy" — the message names agent-2, so its settings are what opens and its node is
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
    expect(await screen.findByRole("dialog")).toHaveAccessibleName("Agent: Judge");
    expect((screen.getByLabelText("Role") as HTMLInputElement).value).toBe("Judge");
  });
});

describe("removing an agent", () => {
  it("takes its settings dialog with it", async () => {
    // The dialog reads the agent out of the draft rather than holding a copy, so the one
    // action inside it that can make its own subject disappear leaves nothing behind.
    await openTheTeam(fakeApi());
    await openAgentSettings("Judge");

    await userEvent.click(screen.getByRole("button", { name: "Remove agent" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.queryByTestId("agent-node-Judge")).not.toBeInTheDocument();
    expect(screen.getByText("unsaved changes")).toBeInTheDocument();
  });
});
