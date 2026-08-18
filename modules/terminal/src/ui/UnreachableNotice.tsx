import type { ReactNode } from "react";
import { Button } from "./Button";

/**
 * "This is not empty — nobody could be asked", with a way to ask again.
 *
 * Eight views said this in their own words and drew the same button beside it. The words
 * stay theirs — an empty archive, an unknown cost and a run nobody is watching are three
 * different sentences, and the module's own message travels intact inside each — but the
 * shape is one: a critical line, the reason, and the retry.
 *
 * `className` replaces rather than extends the default: the padding a notice needs is
 * whatever the view around it gives it (a table cell, a panel header, a whole tab), and
 * two Tailwind text sizes on one element resolve by stylesheet order rather than by the
 * order they were written in.
 */
export function UnreachableNotice({
  children,
  onRetry,
  retryLabel = "Retry",
  className = "text-sm text-critical",
}: {
  /** What could not be read, said in this view's own words, with the module's message. */
  children: ReactNode;
  onRetry(): void;
  /** For the one notice that is not asking for the same read again — the run monitor
   *  opens the stream a second time, which is "Watch again". */
  retryLabel?: string;
  className?: string;
}) {
  return (
    <p className={className}>
      {children}
      <Button size="xs" className="ml-3" onClick={onRetry}>
        {retryLabel}
      </Button>
    </p>
  );
}
