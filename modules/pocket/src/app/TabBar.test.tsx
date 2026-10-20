import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { TabBar } from "./TabBar";

describe("TabBar", () => {
  it("signs out from the bar, and has no such button where there is nothing to end", async () => {
    const onSignOut = vi.fn();
    const { rerender } = render(<TabBar current="markets" onChange={() => {}} onSignOut={onSignOut} />);

    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(onSignOut).toHaveBeenCalledTimes(1);

    rerender(<TabBar current="markets" onChange={() => {}} />);
    expect(screen.queryByRole("button", { name: "Sign out" })).not.toBeInTheDocument();
  });
});
