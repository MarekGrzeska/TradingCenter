import { useRead, type Read } from "../data/query";
import type { TeamsApi, TeamSummary, TeamsModel, TeamsTool } from "./teamsApi";

export type LoadStatus = "loading" | "ready" | "error";

/** One read, once, with a way to ask again — the shape every hook here has, now
 *  `useRead`'s and shared with the rest of the terminal. */
type Loaded<T> = Read<T>;

const NO_TEAMS: TeamSummary[] = [];
const NO_MODELS: TeamsModel[] = [];
const NO_TOOLS: TeamsTool[] = [];

export function useTeams(api: TeamsApi): Loaded<TeamSummary[]> {
  return useRead({
    key: ["teams", "catalogue"],
    read: (signal) => api.listTeams(signal),
    initial: NO_TEAMS,
    fallbackMessage: "could not read the team catalogue",
  });
}

/**
 * What the pickers in the agent panel are built from: the module's model catalogue and
 * whatever its tool server announces. Neither list is ever written down in this
 * terminal (`terminal-teams`, "terminal MUST NOT nieść własnej listy jednych ani
 * drugich") — which is also why the editor waits for the models to arrive before it
 * opens a team at all: a new agent needs a model id, and the only place to get one is
 * here.
 */
export function useModels(api: TeamsApi): Loaded<TeamsModel[]> {
  return useRead({
    key: ["teams", "models"],
    read: (signal) => api.listModels(signal),
    initial: NO_MODELS,
    fallbackMessage: "could not read the model catalogue",
  });
}

export function useTools(api: TeamsApi): Loaded<TeamsTool[]> {
  return useRead({
    key: ["teams", "tools"],
    read: (signal) => api.listTools(signal),
    initial: NO_TOOLS,
    fallbackMessage: "could not read the tool list",
  });
}
