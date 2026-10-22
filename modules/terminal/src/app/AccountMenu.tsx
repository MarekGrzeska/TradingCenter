import { useEffect, useRef, useState } from "react";
import type { Identity, IdentityState } from "../auth/identity";
import { Button } from "../ui/Button";

const LABEL: Record<IdentityState, string> = {
  "signed-in": "Signed in",
  "signed-out": "Signed out",
  unconfigured: "Local mode",
};

const DOT: Record<IdentityState, string> = {
  "signed-in": "bg-good",
  "signed-out": "bg-critical",
  unconfigured: "bg-ink-muted",
};

/** Always on screen, so "am I signed in" is never a question: a terminal with no identity says so rather than
 *  showing nothing, which read as a missing button. The menu opens upward — the button sits at the screen's edge. */
export function AccountMenu({ identity, state }: { identity: Identity; state: IdentityState }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  return (
    <div ref={root} className="relative w-full">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-2 rounded-lg border border-border px-2 py-1.5 text-left text-sm text-ink transition-colors hover:bg-panel-strong"
      >
        <span className={`h-2 w-2 shrink-0 rounded-full ${DOT[state]}`} aria-hidden />
        <span className="flex-1">{LABEL[state]}</span>
        <span aria-hidden className="text-ink-muted">
          ⌃
        </span>
      </button>
      {open && (
        <div
          role="menu"
          className="absolute bottom-full left-0 mb-1 flex w-full flex-col gap-2 rounded-lg border border-border bg-panel p-2 text-xs text-ink-muted shadow-lg"
        >
          {state === "unconfigured" && <p>Sign-in is not configured for this terminal.</p>}
          {state === "signed-out" && (
            <Button tone="primary" size="sm" onClick={() => identity.signIn()}>
              Sign in
            </Button>
          )}
          {state === "signed-in" && (
            <Button tone="critical" size="sm" onClick={() => identity.signOut()}>
              Sign out
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
