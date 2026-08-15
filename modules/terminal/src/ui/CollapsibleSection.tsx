import { useState, type ReactNode } from "react";

/**
 * One named block of a page that can be gotten out of the way, header and body sharing
 * one border so the collapsed state still reads as a whole card and not a stray title.
 * The chevron carries the state visually; the button's own `aria-label` carries it to a
 * screen reader, the same split `ToolCallEntry` uses for a call in the transcript.
 */
export function CollapsibleSection({
  title,
  defaultExpanded = true,
  children,
}: {
  title: string;
  defaultExpanded?: boolean;
  children: ReactNode;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <section className="rounded border border-border bg-panel">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        aria-label={expanded ? `Collapse ${title}` : `Expand ${title}`}
        className="flex w-full cursor-pointer items-center gap-2 px-4 py-2.5 text-left hover:bg-panel-strong"
      >
        <span aria-hidden className="text-ink-faint">
          {expanded ? "▾" : "▸"}
        </span>
        <span className="text-sm font-semibold text-ink">{title}</span>
      </button>
      {expanded && <div className="border-t border-border p-4">{children}</div>}
    </section>
  );
}
