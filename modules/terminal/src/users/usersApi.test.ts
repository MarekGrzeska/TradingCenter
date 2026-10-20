import { afterEach, describe, expect, it, vi } from "vitest";
import { createUsersApi, isEmail, whyNotChange, type Person } from "./usersApi";
import { resolveAccess } from "./accessConfig";

const config = {
  workbenchPrincipal: "wb-sp",
  gatewayPrincipal: "gw-sp",
  roles: { workbenchAdmin: "wb-admin", workbenchViewer: "wb-viewer", gatewayAdmin: "gw-admin" },
  pocketUrl: "https://pocket.example/",
};

type Held = { id: string; principalId: string; appRoleId: string };

/** A directory: the assignments it holds per principal, and every call made against it. */
function directory(initial: Record<string, Held[]> = {}) {
  const held = structuredClone(initial);
  const calls: string[] = [];
  const fetchStub = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    calls.push(`${method} ${url.replace("https://graph.microsoft.com/v1.0", "")}`);
    const json = (body: unknown) =>
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    const principal = /servicePrincipals\/([^/]+)\/appRoleAssignedTo/.exec(url)?.[1];
    if (url.includes("/invitations")) return json({ invitedUser: { id: "new-person" } });
    if (principal && method === "GET") {
      return json({ value: (held[principal] ?? []).map((a) => ({ ...a, principalType: "User" })) });
    }
    if (principal && method === "POST") {
      const body = JSON.parse(String(init?.body)) as Omit<Held, "id">;
      (held[principal] ??= []).push({ id: `a-${calls.length}`, ...body });
      return json({});
    }
    if (principal && method === "DELETE") return new Response(null, { status: 204 });
    return json({});
  });
  vi.stubGlobal("fetch", fetchStub);
  return { calls, held, fetchStub };
}

afterEach(() => vi.unstubAllGlobals());

const signal = new AbortController().signal;

describe("inviting", () => {
  it("gives an admin the role on both APIs and a viewer the workbench one only", async () => {
    const admin = directory();
    await createUsersApi(config).invite("a@example.com", "admin", signal);
    expect(admin.held["wb-sp"]?.map((a) => a.appRoleId)).toEqual(["wb-admin"]);
    expect(admin.held["gw-sp"]?.map((a) => a.appRoleId)).toEqual(["gw-admin"]);

    const viewer = directory();
    await createUsersApi(config).invite("v@example.com", "viewer", signal);
    expect(viewer.held["wb-sp"]?.map((a) => a.appRoleId)).toEqual(["wb-viewer"]);
    expect(viewer.held["gw-sp"] ?? []).toEqual([]);
  });

  it("sends a viewer to the pocket from the e-mail", async () => {
    const dir = directory();
    await createUsersApi(config).invite("v@example.com", "viewer", signal);
    const init = dir.fetchStub.mock.calls[0]?.[1] as RequestInit;
    expect(JSON.parse(String(init.body))).toMatchObject({
      invitedUserEmailAddress: "v@example.com",
      inviteRedirectUrl: "https://pocket.example/",
      sendInvitationMessage: true,
    });
  });
});

describe("changing a role", () => {
  it("promotes a viewer: adds the admin roles and removes the viewer one", async () => {
    const dir = directory({ "wb-sp": [{ id: "x1", principalId: "p1", appRoleId: "wb-viewer" }] });
    await createUsersApi(config).setRole("p1", "admin", signal);
    expect(dir.calls).toContain("DELETE /servicePrincipals/wb-sp/appRoleAssignedTo/x1");
    expect(dir.held["gw-sp"]?.map((a) => a.appRoleId)).toEqual(["gw-admin"]);
  });

  it("takes every assignment away on revoke", async () => {
    const dir = directory({
      "wb-sp": [{ id: "x1", principalId: "p1", appRoleId: "wb-admin" }],
      "gw-sp": [{ id: "x2", principalId: "p1", appRoleId: "gw-admin" }],
    });
    await createUsersApi(config).setRole("p1", null, signal);
    expect(dir.calls.filter((c) => c.startsWith("DELETE"))).toHaveLength(2);
  });
});

describe("guards", () => {
  const admin = (id: string): Person => ({ id, name: id, email: id, role: "admin", pending: false });
  const viewer: Person = { id: "v", name: "v", email: "v", role: "viewer", pending: false };

  it("refuses the last admin and the own admin role, and nothing else", () => {
    expect(whyNotChange([admin("a")], admin("a"), "viewer", "someone-else")).toMatch(/last admin/);
    expect(whyNotChange([admin("a"), admin("b")], admin("a"), null, "a")).toMatch(/own admin/);
    expect(whyNotChange([admin("a"), admin("b")], admin("a"), null, "b")).toBeNull();
    expect(whyNotChange([admin("a"), viewer], viewer, null, "a")).toBeNull();
  });

  it("recognises an address", () => {
    expect(isEmail(" a@b.co ")).toBe(true);
    expect(isEmail("not an address")).toBe(false);
  });
});

describe("configuration", () => {
  it("is absent without the directory ids, and refuses half of them", () => {
    expect(resolveAccess({ VITE_POCKET_URL: "https://p/" })).toBeNull();
    expect(() =>
      resolveAccess({ VITE_ACCESS_WORKBENCH_PRINCIPAL: "x", VITE_POCKET_URL: "https://p/" }),
    ).toThrow();
  });
});
