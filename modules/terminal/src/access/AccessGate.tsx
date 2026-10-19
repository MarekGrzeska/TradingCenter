import { useEffect, useMemo, useState, type ReactNode } from "react";
import { workbenchIdentity } from "../data/marketData";
import { resolveEndpoints } from "../data/config";
import { Button } from "../ui/Button";
import { ADMIN_ROLE, createAccessApi, type AccessApi } from "./accessApi";

type Verdict = "asking" | "allowed" | "refused";

/**
 * The terminal is the admin's screen: a signed-in person without that role gets a page that says so instead of a tab bar
 * full of refusals. This is a courtesy — every route refuses them anyway. An answer that cannot be had (the workbench is
 * down, the session is gone) lets the terminal render as it always did, with its own notices; locking the operator out
 * of the screen that shows them the outage would be the worse failure.
 */
export function AccessGate({
  children,
  api,
  signOut = () => workbenchIdentity.signIn(),
}: {
  children: ReactNode;
  api?: AccessApi;
  signOut?: () => void;
}) {
  const client = useMemo(
    () => api ?? createAccessApi(resolveEndpoints().workbenchHttp, workbenchIdentity),
    [api],
  );
  const [verdict, setVerdict] = useState<Verdict>(
    api === undefined && workbenchIdentity.state() === "unconfigured" ? "allowed" : "asking",
  );

  useEffect(() => {
    if (verdict !== "asking") return;
    const controller = new AbortController();
    client
      .me(controller.signal)
      .then((me) => setVerdict(me.roles.includes(ADMIN_ROLE) ? "allowed" : "refused"))
      .catch(() => {
        if (!controller.signal.aborted) setVerdict("allowed");
      });
    return () => controller.abort();
  }, [client, verdict]);

  if (verdict === "asking") return null;
  if (verdict === "allowed") return <>{children}</>;

  return (
    <main className="flex h-screen flex-col items-center justify-center gap-3 bg-canvas p-6 text-center text-ink">
      <h1 className="text-lg font-semibold">No access to the terminal</h1>
      <p className="max-w-md text-sm text-ink-secondary">
        This account can use the pocket, not the terminal. If you expected the terminal, ask an admin
        for the admin role, then sign in again.
      </p>
      <Button size="md" onClick={signOut}>
        Sign in again
      </Button>
    </main>
  );
}
