import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MarketDataError } from "../data/types";
import { TeamsView } from "./TeamsView";
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

function fakeApi(overrides: Partial<TeamsApi> = {}): TeamsApi {
  return {
    listModels: vi.fn(async () => MODELS),
    listTools: vi.fn(async () => [{ name: "get_candles", description: "candles from the archive" }]),
    listTeams: vi.fn(async () => [TEAM]),
    createTeam: vi.fn(async () => TEAM),
    getTeam: vi.fn(async () => TEAM),
    latestRevision: vi.fn(async () => revision()),
    getRevision: vi.fn(async () => revision()),
    saveRevision: vi.fn(async () => revision()),
    archiveTeam: vi.fn(async () => {}),
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
