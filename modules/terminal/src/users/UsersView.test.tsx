import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { UsersView } from "./UsersView";
import type { Person, UsersApi } from "./usersApi";

const admin: Person = { id: "me", name: "Op", email: "op@example.com", role: "admin", pending: false };
const viewer: Person = { id: "v1", name: "V", email: "v@example.com", role: "viewer", pending: true };

function fakeApi(people: Person[] = [admin, viewer]) {
  const api: UsersApi = {
    list: vi.fn(async () => people),
    invite: vi.fn(async () => {}),
    setRole: vi.fn(async () => {}),
  };
  return api;
}

describe("UsersView", () => {
  it("lists who has access and invites an address as a viewer", async () => {
    const api = fakeApi();
    render(<UsersView api={api} selfId="me" />);
    expect(await screen.findByText("v@example.com")).toBeInTheDocument();
    expect(screen.getByText("invited, not signed in yet")).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("E-mail to invite"), "new@gmail.com");
    await userEvent.click(screen.getByRole("button", { name: "Invite" }));

    await waitFor(() =>
      expect(api.invite).toHaveBeenCalledWith("new@gmail.com", "viewer", expect.anything()),
    );
  });

  it("does not call the directory for something that is not an address", async () => {
    const api = fakeApi();
    render(<UsersView api={api} selfId="me" />);
    await screen.findByText("v@example.com");

    await userEvent.type(screen.getByLabelText("E-mail to invite"), "nope");
    await userEvent.click(screen.getByRole("button", { name: "Invite" }));

    expect(await screen.findByText("that is not an e-mail address")).toBeInTheDocument();
    expect(api.invite).not.toHaveBeenCalled();
  });

  it("refuses to take the admin role from the signed-in admin", async () => {
    const api = fakeApi([admin, viewer]);
    render(<UsersView api={api} selfId="me" />);
    await screen.findByText("op@example.com");

    await userEvent.selectOptions(screen.getByLabelText("Role of op@example.com"), "viewer");

    expect(await screen.findByText(/own admin role/)).toBeInTheDocument();
    expect(api.setRole).not.toHaveBeenCalled();
  });
});
