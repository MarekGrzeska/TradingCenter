import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MarketDataError } from "../data/types";
import { MemoryPanel } from "./MemoryPanel";
import type { TeamMemory, TeamsApi } from "./teamsApi";

/** Only the two calls this panel makes. Everything else on `TeamsApi` is another view's,
 *  and stubbing it here would be a list to keep in step for nothing. */
function fakeApi(overrides: Partial<TeamsApi> = {}): TeamsApi {
  return {
    memory: vi.fn(async () => ({ entries: [], total: 0 }) as TeamMemory),
    deleteMemory: vi.fn(async () => {}),
    ...overrides,
  } as unknown as TeamsApi;
}

const ENTRY = {
  id: 7,
  authorAgentKey: "scout",
  runId: 12,
  content: "gaps at the open usually close by noon",
  createdAt: 1_755_000_000,
};

function renderPanel(api: TeamsApi) {
  return render(
    <MemoryPanel api={api} teamId={1} teamName="Morning desk" onClose={vi.fn()} />,
  );
}

describe("what a team remembers", () => {
  it("lists the notes with the agent that wrote each one", async () => {
    renderPanel(fakeApi({ memory: vi.fn(async () => ({ entries: [ENTRY], total: 1 })) }));

    expect(await screen.findByText(ENTRY.content)).toBeInTheDocument();
    expect(screen.getByText("scout")).toBeInTheDocument();
    expect(screen.getByText("run #12")).toBeInTheDocument();
  });

  it("says a team has remembered nothing rather than showing an empty box", async () => {
    // specs/terminal-teams: no memory is the ordinary state, and the only one for a team
    // whose agents carry no memory tools.
    renderPanel(fakeApi());

    expect(await screen.findByText(/has not remembered anything yet/i)).toBeInTheDocument();
  });

  it("says how many notes it is not showing", async () => {
    renderPanel(
      fakeApi({ memory: vi.fn(async () => ({ entries: [ENTRY], total: 40 })) }),
    );

    expect(await screen.findByText(/showing the 1 newest of 40 notes/i)).toBeInTheDocument();
  });

  it("names the failure instead of reading as a team with no memory", async () => {
    const api = fakeApi({
      memory: vi.fn(async () => {
        throw new MarketDataError("unreachable", "the workbench is not answering");
      }),
    });

    renderPanel(api);

    expect(await screen.findByText(/not answering/i)).toBeInTheDocument();
    expect(screen.queryByText(/has not remembered anything yet/i)).not.toBeInTheDocument();
  });
});

describe("removing a note", () => {
  it("asks first, then removes the one the operator picked", async () => {
    const deleteMemory = vi.fn(async () => {});
    const api = fakeApi({
      memory: vi.fn(async () => ({ entries: [ENTRY], total: 1 })),
      deleteMemory,
    });
    renderPanel(api);
    await screen.findByText(ENTRY.content);

    await userEvent.click(screen.getByRole("button", { name: /remove/i }));
    expect(await screen.findByText(/remove this note\?/i)).toBeInTheDocument();
    expect(deleteMemory).not.toHaveBeenCalled();

    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Remove" }),
    );

    await waitFor(() => expect(deleteMemory).toHaveBeenCalledWith(1, 7, expect.anything()));
  });

  it("keeps the refusal beside the question it explains", async () => {
    const api = fakeApi({
      memory: vi.fn(async () => ({ entries: [ENTRY], total: 1 })),
      deleteMemory: vi.fn(async () => {
        throw new MarketDataError("refused", "no such memory entry");
      }),
    });
    renderPanel(api);
    await screen.findByText(ENTRY.content);
    await userEvent.click(screen.getByRole("button", { name: /remove/i }));
    await screen.findByText(/remove this note\?/i);

    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Remove" }),
    );

    expect(await screen.findByText(/no such memory entry/i)).toBeInTheDocument();
    // Still up: a message thrown at the view the dialog just left has lost its decision.
    expect(screen.getByText(/remove this note\?/i)).toBeInTheDocument();
  });

  it("does not offer any way to write or edit a note", async () => {
    renderPanel(fakeApi({ memory: vi.fn(async () => ({ entries: [ENTRY], total: 1 })) }));
    await screen.findByText(ENTRY.content);

    // A note is an agent's decision and a correction is the next note — the operator's
    // part is removal only (specs/teams-memory).
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /add|save|edit/i })).not.toBeInTheDocument();
  });
});
