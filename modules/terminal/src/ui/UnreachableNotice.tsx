import type { ReactNode } from "react";
import { Button } from "./Button";

/**
 * "This is not empty — nobody could be asked", with a way to ask again. The words stay each view's; the shape is one.
 * `className` replaces rather than extends: two Tailwind text sizes on one element resolve by stylesheet order.
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
