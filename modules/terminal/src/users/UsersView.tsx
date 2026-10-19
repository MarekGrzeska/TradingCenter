import { useMemo, useState, type FormEvent } from "react";
import { createAccessApi } from "../access/accessApi";
import { resolveEndpoints } from "../data/config";
import { graphIdentity, workbenchIdentity } from "../data/marketData";
import { useRead } from "../data/query";
import { Button } from "../ui/Button";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { UnreachableNotice } from "../ui/UnreachableNotice";
import { resolveAccess } from "./accessConfig";
import {
  createUsersApi,
  isEmail,
  whyNotChange,
  type Person,
  type Role,
  type UsersApi,
} from "./usersApi";

const NO_PEOPLE: Person[] = [];

/**
 * Who may use the system, and as what. A change reaches a person when their token next renews — within the hour — and the
 * screen says so, because "I changed it and nothing happened" is otherwise the first report.
 */
export function UsersView({ api, selfId }: { api?: UsersApi; selfId?: string } = {}) {
  const config = useMemo(() => (api ? null : resolveAccess()), [api]);
  const client = useMemo(
    () => api ?? (config ? createUsersApi(config, graphIdentity) : null),
    [api, config],
  );

  if (client === null) {
    return (
      <section className="p-4 text-sm text-ink-secondary">
        User management is not set up in this build: it needs the directory identifiers from Terraform
        (VITE_ACCESS_*) and a signed-in admin.
      </section>
    );
  }
  return <Users client={client} selfId={selfId} />;
}

function Users({ client, selfId }: { client: UsersApi; selfId: string | undefined }) {
  const me = useRead({
    key: ["access", "me"],
    read: (signal) =>
      selfId !== undefined
        ? Promise.resolve({ roles: ["admin"], person: selfId })
        : createAccessApi(resolveEndpoints().workbenchHttp, workbenchIdentity).me(signal),
    initial: { roles: [] as string[], person: "" },
    fallbackMessage: "could not read who you are",
  });
  const people = useRead<Person[]>({
    key: ["users"],
    read: (signal) => client.list(signal),
    initial: NO_PEOPLE,
    fallbackMessage: "could not read the users",
  });

  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("viewer");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [revoking, setRevoking] = useState<Person | null>(null);

  async function run(work: (signal: AbortSignal) => Promise<void>, failure: string) {
    setBusy(true);
    setNotice(null);
    try {
      await work(new AbortController().signal);
      people.reload();
    } catch (cause) {
      setNotice(`${failure}${cause instanceof Error && cause.message ? ` — ${cause.message}` : ""}`);
    } finally {
      setBusy(false);
    }
  }

  function invite(event: FormEvent) {
    event.preventDefault();
    const address = email.trim();
    if (!isEmail(address)) {
      setNotice("that is not an e-mail address");
      return;
    }
    void run(async (signal) => {
      await client.invite(address, role, signal);
      setEmail("");
      setNotice(`invited ${address} as ${role}`);
    }, "could not invite");
  }

  function change(person: Person, next: Role | null) {
    const why = whyNotChange(people.value, person, next, me.value.person);
    if (why !== null) {
      setNotice(why);
      return;
    }
    void run((signal) => client.setRole(person.id, next, signal), "could not change the role");
  }

  const refusalOfRevoke = revoking && whyNotChange(people.value, revoking, null, me.value.person);

  return (
    <section className="flex h-full min-h-0 flex-col gap-4 p-4">
      <header className="flex items-center gap-3">
        <h1 className="text-base font-semibold text-ink">Users</h1>
        <span className="text-xs text-ink-faint">
          a change reaches a person when their sign-in next renews, within about an hour
        </span>
      </header>

      <form onSubmit={invite} className="flex flex-wrap items-center gap-2">
        <input
          aria-label="E-mail to invite"
          type="text"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="name@example.com — any address"
          className="w-72 rounded border border-border bg-panel px-2 py-1 text-sm text-ink"
        />
        <select
          aria-label="Role of the invited"
          value={role}
          onChange={(event) => setRole(event.target.value as Role)}
          className="rounded border border-border bg-panel px-2 py-1 text-sm text-ink"
        >
          <option value="viewer">viewer — pocket, read only</option>
          <option value="admin">admin — everything</option>
        </select>
        <Button type="submit" tone="primary" size="md" disabled={busy}>
          Invite
        </Button>
      </form>

      {notice !== null && (
        <p role="status" className="text-sm text-ink-secondary">
          {notice}
        </p>
      )}
      {people.error !== null && (
        <UnreachableNotice onRetry={people.reload}>
          The users could not be read — {people.error}.
        </UnreachableNotice>
      )}

      <div className="overflow-x-auto rounded border border-border">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border text-left text-ink-faint">
              <th className="px-3 py-2 font-medium">Person</th>
              <th className="px-3 py-2 font-medium">E-mail</th>
              <th className="px-3 py-2 font-medium">Role</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {people.value.map((person) => (
              <tr key={person.id} className="border-b border-border last:border-b-0">
                <td className="px-3 py-2 text-ink">{person.name}</td>
                <td className="px-3 py-2 text-ink-secondary">{person.email}</td>
                <td className="px-3 py-2">
                  <select
                    aria-label={`Role of ${person.email}`}
                    value={person.role}
                    disabled={busy}
                    onChange={(event) => change(person, event.target.value as Role)}
                    className="rounded border border-border bg-panel px-1 py-0.5 text-xs text-ink"
                  >
                    <option value="viewer">viewer</option>
                    <option value="admin">admin</option>
                  </select>
                </td>
                <td className="px-3 py-2 text-ink-secondary">
                  {person.pending ? "invited, not signed in yet" : "active"}
                </td>
                <td className="px-3 py-2 text-right">
                  <Button size="2xs" tone="critical" onClick={() => setRevoking(person)}>
                    Remove access
                  </Button>
                </td>
              </tr>
            ))}
            {people.status === "loading" && people.value.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-3 text-ink-faint">
                  reading the users…
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {revoking !== null && (
        <ConfirmDialog
          title={`Remove access for ${revoking.email}?`}
          confirmLabel="Remove access"
          busyLabel="Removing…"
          tone="danger"
          confirmDisabled={refusalOfRevoke !== null}
          onConfirm={async () => {
            await client.setRole(revoking.id, null, new AbortController().signal);
            people.reload();
          }}
          onClose={() => setRevoking(null)}
        >
          {refusalOfRevoke ? (
            <p className="text-sm text-critical">{refusalOfRevoke}.</p>
          ) : (
            <p className="text-sm text-ink-secondary">
              They stay in the directory as a guest, with no role and so no access, until their sign-in
              renews and then for good.
            </p>
          )}
        </ConfirmDialog>
      )}
    </section>
  );
}
