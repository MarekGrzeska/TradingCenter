import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { PromptManagementView } from "./PromptManagementView";
import type { AgentApi, AgentPrompt } from "../agentApi";
import { MarketDataError } from "../../data/types";

function promptFixture(overrides: Partial<AgentPrompt> = {}): AgentPrompt {
  return {
    version: "v4",
    withTools: "you have read-only tools",
    withoutTools: "you have no tools",
    updatedAt: 1786442400,
    ...overrides,
  };
}

function fakeApi(overrides: Partial<AgentApi> = {}): AgentApi {
  return {
    listModels: async () => [],
    listSessions: async () => [],
    getSession: async () => {
      throw new Error("not used");
    },
    createSession: async () => {
      throw new Error("not used");
    },
    setSessionModel: async () => {
      throw new Error("not used");
    },
    renameSession: async () => {
      throw new Error("not used");
    },
    deleteSession: async () => {
      throw new Error("not used");
    },
    getMessages: async () => [],
    sendMessage: async () => {
      throw new Error("not used");
    },
    usage: async () => {
      throw new Error("not used");
    },
    getPrompt: async () => promptFixture(),
    updatePrompt: async () => promptFixture(),
    chartCommand: async () => null,
    listDrawings: async () => [],
    patchDrawing: async () => {
      throw new Error("not used in this test");
    },
    deleteDrawing: async () => {},
    ...overrides,
  };
}

describe("PromptManagementView", () => {
  it("reads the current version and both variants from the module", async () => {
    render(<PromptManagementView api={fakeApi()} />);

    await screen.findByText("v4");
    expect(screen.getByLabelText("With tools")).toHaveValue("you have read-only tools");
    expect(screen.getByLabelText("Without tools")).toHaveValue("you have no tools");
  });

  it("says the module is unreachable and shows no content as current", async () => {
    const api = fakeApi({
      getPrompt: async () => {
        throw new Error("agent is not reachable");
      },
    });
    render(<PromptManagementView api={api} />);

    await screen.findByText(/agent module is not reachable/i);
    expect(screen.queryByLabelText("With tools")).not.toBeInTheDocument();
  });

  it("sends both variants on save and shows the version the module returns", async () => {
    let sent: [string, string] | null = null;
    const api = fakeApi({
      updatePrompt: async (withTools, withoutTools) => {
        sent = [withTools, withoutTools];
        return promptFixture({ version: "v5", withTools, withoutTools });
      },
    });
    const user = userEvent.setup();
    render(<PromptManagementView api={api} />);
    await screen.findByText("v4");

    await user.clear(screen.getByLabelText("With tools"));
    await user.type(screen.getByLabelText("With tools"), "edited");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await screen.findByText("v5");
    expect(sent).toEqual(["edited", "you have no tools"]);
  });

  it("keeps the last confirmed content on screen when a save is refused", async () => {
    const api = fakeApi({
      updatePrompt: async () => {
        throw new MarketDataError("refused", "with_tools is blank");
      },
    });
    const user = userEvent.setup();
    render(<PromptManagementView api={api} />);
    await screen.findByText("v4");

    await user.clear(screen.getByLabelText("With tools"));
    await user.click(screen.getByRole("button", { name: /save/i }));

    await screen.findByText(/with_tools is blank/i);
    // The version stays the one the module last confirmed — a refused save is not a
    // save, and the section must not act as though it were.
    expect(screen.getByText("v4")).toBeInTheDocument();
  });

  it("locks the fields while a save is in flight, so a keystroke cannot land between submit and response", async () => {
    let resolveSave: (value: AgentPrompt) => void = () => {};
    const api = fakeApi({
      updatePrompt: async () =>
        new Promise<AgentPrompt>((resolve) => {
          resolveSave = resolve;
        }),
    });
    const user = userEvent.setup();
    render(<PromptManagementView api={api} />);
    await screen.findByText("v4");

    await user.type(screen.getByLabelText("With tools"), " more");
    await user.click(screen.getByRole("button", { name: /save/i }));

    expect(screen.getByLabelText("With tools")).toBeDisabled();

    resolveSave(promptFixture({ version: "v5", withTools: "you have read-only tools more" }));
    await screen.findByText("v5");
    expect(screen.getByLabelText("With tools")).not.toBeDisabled();
  });

  it("disables Save until something actually changed", async () => {
    render(<PromptManagementView api={fakeApi()} />);
    await screen.findByText("v4");

    expect(screen.getByRole("button", { name: /^save$/i })).toBeDisabled();
  });

  it("re-reads from the module every time the section mounts", async () => {
    let calls = 0;
    const api = fakeApi({
      getPrompt: async () => {
        calls += 1;
        return promptFixture();
      },
    });
    const { unmount } = render(<PromptManagementView api={api} />);
    await waitFor(() => expect(calls).toBe(1));
    unmount();

    render(<PromptManagementView api={api} />);
    await waitFor(() => expect(calls).toBe(2));
  });
});
