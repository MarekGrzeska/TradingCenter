import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { CollapsibleSection } from "./CollapsibleSection";

describe("CollapsibleSection", () => {
  it("shows its body by default", () => {
    render(
      <CollapsibleSection title="Agent cost">
        <p>body text</p>
      </CollapsibleSection>,
    );
    expect(screen.getByText("body text")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /collapse agent cost/i })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  it("starts collapsed when told to", () => {
    render(
      <CollapsibleSection title="Agent cost" defaultExpanded={false}>
        <p>body text</p>
      </CollapsibleSection>,
    );
    expect(screen.queryByText("body text")).not.toBeInTheDocument();
  });

  it("toggles the body on click, without unmounting the rest of the page around it", async () => {
    const user = userEvent.setup();
    render(
      <CollapsibleSection title="Agent cost">
        <p>body text</p>
      </CollapsibleSection>,
    );

    await user.click(screen.getByRole("button", { name: /collapse agent cost/i }));
    expect(screen.queryByText("body text")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /expand agent cost/i })).toHaveAttribute(
      "aria-expanded",
      "false",
    );

    await user.click(screen.getByRole("button", { name: /expand agent cost/i }));
    expect(screen.getByText("body text")).toBeInTheDocument();
  });
});
