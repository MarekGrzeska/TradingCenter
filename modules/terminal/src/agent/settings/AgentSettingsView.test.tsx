import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AgentSettingsView } from "./AgentSettingsView";

describe("AgentSettingsView", () => {
  it("shows the cost section expanded by default", async () => {
    render(<AgentSettingsView />);
    expect(screen.getByRole("button", { name: /collapse agent cost/i })).toBeInTheDocument();
    await screen.findByLabelText("From");
  });

  it("collapses the cost section fully, rather than just shrinking it", async () => {
    const user = userEvent.setup();
    render(<AgentSettingsView />);
    await screen.findByLabelText("From");

    await user.click(screen.getByRole("button", { name: /collapse agent cost/i }));

    expect(screen.queryByLabelText("From")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /expand agent cost/i })).toBeInTheDocument();
  });
});
