/**
 * The people who may use this system, managed in the directory itself through Microsoft Graph with the signed-in admin's own
 * token. No module of this system holds a credential that can write the directory, and none is asked to: what a person can
 * do here is the intersection of this tab's consent and their own directory roles.
 */

import { noIdentity, type Identity } from "../auth/identity";
import { jsonClient, statusMapper } from "../data/http";
import type { AccessConfig } from "./accessConfig";

export type Role = "admin" | "viewer";

export interface Person {
  id: string;
  name: string;
  email: string;
  role: Role;
  /** Invited and not yet signed in. */
  pending: boolean;
}

export interface UsersApi {
  list(signal: AbortSignal): Promise<Person[]>;
  invite(email: string, role: Role, signal: AbortSignal): Promise<void>;
  /** `null` takes the access away. */
  setRole(personId: string, role: Role | null, signal: AbortSignal): Promise<void>;
}

const GRAPH = "https://graph.microsoft.com/v1.0";

interface Assignment {
  id: string;
  principalId: string;
  principalType: string;
  appRoleId: string;
}

interface GraphUser {
  id: string;
  displayName: string | null;
  mail: string | null;
  userPrincipalName: string;
  externalUserState: string | null;
}

// Graph's own reason is in `error.message`, which the shared client does not read; the status says enough for a notice.
const mapStatus = statusMapper({ 400: "refused", 403: "refused", 404: "not-found", 409: "refused" });

export function createUsersApi(
  config: AccessConfig,
  identity: Identity = noIdentity,
  base: string = GRAPH,
): UsersApi {
  const http = jsonClient("Microsoft Graph", mapStatus, identity);
  const { roles } = config;

  async function assignments(principal: string, signal: AbortSignal): Promise<Assignment[]> {
    const page = await http.json<{ value: Assignment[] }>(
      `${base}/servicePrincipals/${principal}/appRoleAssignedTo?$top=999`,
      { signal },
    );
    return page.value.filter((entry) => entry.principalType === "User");
  }

  /** The assignments a role means: the workbench's role, plus the gateway's for an admin — a viewer holds nothing there. */
  function wanted(role: Role | null): { principal: string; roleId: string }[] {
    if (role === "admin") {
      return [
        { principal: config.workbenchPrincipal, roleId: roles.workbenchAdmin },
        { principal: config.gatewayPrincipal, roleId: roles.gatewayAdmin },
      ];
    }
    if (role === "viewer") {
      return [{ principal: config.workbenchPrincipal, roleId: roles.workbenchViewer }];
    }
    return [];
  }

  async function setRole(personId: string, role: Role | null, signal: AbortSignal): Promise<void> {
    const target = wanted(role);
    for (const principal of [config.workbenchPrincipal, config.gatewayPrincipal]) {
      const held = (await assignments(principal, signal)).filter(
        (entry) => entry.principalId === personId,
      );
      const keep = new Set(
        target.filter((entry) => entry.principal === principal).map((entry) => entry.roleId),
      );
      // Added before removed, so a failure in between leaves the person with too much for a moment rather than locked out.
      const heldIds = new Set(held.map((entry) => entry.appRoleId));
      for (const roleId of keep) {
        if (heldIds.has(roleId)) continue;
        await http.json(`${base}/servicePrincipals/${principal}/appRoleAssignedTo`, {
          method: "POST",
          body: { principalId: personId, resourceId: principal, appRoleId: roleId },
          signal,
        });
      }
      for (const entry of held) {
        if (!keep.has(entry.appRoleId)) {
          await http.send(`${base}/servicePrincipals/${principal}/appRoleAssignedTo/${entry.id}`, {
            method: "DELETE",
            signal,
          });
        }
      }
    }
  }

  return {
    async list(signal) {
      const held = await assignments(config.workbenchPrincipal, signal);
      const roleOf = new Map<string, Role>();
      for (const entry of held) {
        if (entry.appRoleId === roles.workbenchAdmin) roleOf.set(entry.principalId, "admin");
        else if (entry.appRoleId === roles.workbenchViewer && !roleOf.has(entry.principalId)) {
          roleOf.set(entry.principalId, "viewer");
        }
      }
      const people = await Promise.all(
        [...roleOf].map(async ([id, role]): Promise<Person> => {
          const user = await http.json<GraphUser>(
            `${base}/users/${id}?$select=id,displayName,mail,userPrincipalName,externalUserState`,
            { signal },
          );
          return {
            id,
            name: user.displayName ?? user.userPrincipalName,
            email: user.mail ?? user.userPrincipalName,
            role,
            pending: user.externalUserState === "PendingAcceptance",
          };
        }),
      );
      return people.sort((a, b) => a.email.localeCompare(b.email));
    },

    async invite(email, role, signal) {
      const invitation = await http.json<{ invitedUser: { id: string } }>(`${base}/invitations`, {
        method: "POST",
        body: {
          invitedUserEmailAddress: email,
          // The place the e-mail leads: the phone for a viewer, the terminal for an admin.
          inviteRedirectUrl: role === "viewer" ? config.pocketUrl : window.location.origin,
          sendInvitationMessage: true,
        },
        signal,
      });
      await setRole(invitation.invitedUser.id, role, signal);
    },

    setRole,
  };
}

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function isEmail(value: string): boolean {
  return EMAIL.test(value.trim());
}

/** Why a change to `target` must not happen, or `null`. Refusing the last admin and one's own admin role keeps the application
 *  from ending with nobody who can repair it. */
export function whyNotChange(
  people: Person[],
  target: Person,
  next: Role | null,
  selfId: string,
): string | null {
  if (target.role !== "admin" || next === "admin") return null;
  if (target.id === selfId) return "you cannot take away your own admin role";
  if (people.filter((person) => person.role === "admin").length <= 1) return "this is the last admin";
  return null;
}
