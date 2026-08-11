import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AgentChat } from "./AgentChat";
import { createAgentChatStore, STORAGE_KEY } from "./agentChatStore";

function renderChat(storage: Storage | null = null) {
  const store = createAgentChatStore(storage);
  return { store, ...render(<AgentChat store={store} />) };
}

describe("AgentChat", () => {
  it("starts collapsed, offering the rail and nothing else", () => {
    renderChat();

    expect(screen.getByRole("button", { name: /open agent chat/i })).toBeInTheDocument();
    expect(screen.queryByRole("complementary", { name: /agent chat/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /message the agent/i })).not.toBeInTheDocument();
  });

  it("expands from the rail and collapses back to it", async () => {
    const user = userEvent.setup();
    renderChat();

    await user.click(screen.getByRole("button", { name: /open agent chat/i }));

    expect(screen.getByRole("complementary", { name: /agent chat/i })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /message the agent/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /open agent chat/i })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /collapse agent chat/i }));

    expect(screen.getByRole("button", { name: /open agent chat/i })).toBeInTheDocument();
    expect(screen.queryByRole("complementary", { name: /agent chat/i })).not.toBeInTheDocument();
  });

  it("appends the operator's turn and a reply, and empties the box", async () => {
    const user = userEvent.setup();
    renderChat();
    await user.click(screen.getByRole("button", { name: /open agent chat/i }));

    const box = screen.getByRole("textbox", { name: /message the agent/i });
    await user.type(box, "why is BTC flat");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(screen.getByText("why is BTC flat")).toBeInTheDocument();
    expect(screen.getAllByText(/still a mockup/i)).toHaveLength(1);
    expect(box).toHaveValue("");
  });

  it("sends on Enter and breaks the line on Shift+Enter", async () => {
    const user = userEvent.setup();
    renderChat();
    await user.click(screen.getByRole("button", { name: /open agent chat/i }));

    const box = screen.getByRole("textbox", { name: /message the agent/i });
    await user.type(box, "one{Shift>}{Enter}{/Shift}two");

    expect(box).toHaveValue("one\ntwo");
    expect(screen.queryByText(/still a mockup/i)).not.toBeInTheDocument();

    await user.type(box, "{Enter}");

    expect(screen.getByText("one two")).toBeInTheDocument();
    expect(box).toHaveValue("");
  });

  it("ignores an empty send rather than posting a blank turn", async () => {
    const user = userEvent.setup();
    renderChat();
    await user.click(screen.getByRole("button", { name: /open agent chat/i }));

    const box = screen.getByRole("textbox", { name: /message the agent/i });
    await user.type(box, "   {Enter}");

    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(screen.queryByText(/still a mockup/i)).not.toBeInTheDocument();
  });

  // The panel takes width from the charts, so an operator who closed it must not find it
  // open again after a reload.
  it("remembers whether it was open", async () => {
    const user = userEvent.setup();
    renderChat(window.localStorage);

    await user.click(screen.getByRole("button", { name: /open agent chat/i }));
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe("expanded");

    const second = createAgentChatStore(window.localStorage);
    expect(second.getSnapshot().expanded).toBe(true);

    await user.click(screen.getByRole("button", { name: /collapse agent chat/i }));
    expect(createAgentChatStore(window.localStorage).getSnapshot().expanded).toBe(false);
  });
});
