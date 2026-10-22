import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { noIdentity, type Identity, type IdentityState } from "../auth/identity";
import { AccountMenu } from "./AccountMenu";

function setup(state: IdentityState) {
  const identity: Identity = { ...noIdentity, signIn: vi.fn(), signOut: vi.fn() };
  render(<AccountMenu identity={identity} state={state} />);
  return identity;
}

describe("AccountMenu", () => {
  it("offers sign out to a signed-in operator", async () => {
    const user = userEvent.setup();
    const identity = setup("signed-in");

    await user.click(screen.getByRole("button", { name: /signed in/i }));
    await user.click(screen.getByRole("button", { name: "Sign out" }));

    expect(identity.signOut).toHaveBeenCalledOnce();
  });

  it("offers sign in to a signed-out operator", async () => {
    const user = userEvent.setup();
    const identity = setup("signed-out");

    await user.click(screen.getByRole("button", { name: /signed out/i }));
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(identity.signIn).toHaveBeenCalledOnce();
  });

  it("says so, with no action, when no identity is configured", async () => {
    const user = userEvent.setup();
    setup("unconfigured");

    await user.click(screen.getByRole("button", { name: /local mode/i }));

    expect(screen.getByText(/not configured/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /sign (in|out)/i })).not.toBeInTheDocument();
  });
});
