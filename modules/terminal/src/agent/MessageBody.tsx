import type { ReactNode } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remend from "remend";

/**
 * Model prose as the Markdown the model writes; the operator's own messages are not rendered this way. No
 * `rehype-raw`, on purpose: raw HTML is then not rendered at all, and the whole safety argument is its absence.
 */

/**
 * `remend` closes what the stream has not finished saying, so a half-written `**` is bold from the first frame.
 * `linkMode` "text-only" avoids a clickable non-link; `katex` false because costs are written `$0.2` here.
 */
const REMEND_OPTIONS = { linkMode: "text-only", katex: false } as const;

/**
 * Mapped onto the terminal's own tokens rather than left to a stylesheet: this is the reason
 * `react-markdown` is here instead of `streamdown`, which brings a look this panel does not have.
 */
const COMPONENTS = {
  p: ({ children }: { children?: ReactNode }) => <p className="mb-2 last:mb-0">{children}</p>,
  ul: ({ children }: { children?: ReactNode }) => (
    <ul className="mb-2 list-disc pl-4 last:mb-0">{children}</ul>
  ),
  ol: ({ children }: { children?: ReactNode }) => (
    <ol className="mb-2 list-decimal pl-4 last:mb-0">{children}</ol>
  ),
  li: ({ children }: { children?: ReactNode }) => <li className="mb-0.5">{children}</li>,
  strong: ({ children }: { children?: ReactNode }) => (
    <strong className="font-semibold text-ink">{children}</strong>
  ),
  em: ({ children }: { children?: ReactNode }) => <em className="italic">{children}</em>,
  // Headings are flattened to bold text. A reply inside a 460px bubble has no document
  // outline to carry, and a real `h1` here would outrank the panel's own header.
  h1: ({ children }: { children?: ReactNode }) => <Heading>{children}</Heading>,
  h2: ({ children }: { children?: ReactNode }) => <Heading>{children}</Heading>,
  h3: ({ children }: { children?: ReactNode }) => <Heading>{children}</Heading>,
  h4: ({ children }: { children?: ReactNode }) => <Heading>{children}</Heading>,
  h5: ({ children }: { children?: ReactNode }) => <Heading>{children}</Heading>,
  h6: ({ children }: { children?: ReactNode }) => <Heading>{children}</Heading>,
  code: ({ children }: { children?: ReactNode }) => (
    <code className="rounded bg-sunken px-1 py-0.5 font-mono text-[11px] text-ink">{children}</code>
  ),
  // The `code` above nests inside this, so the block gets the scroll and the padding and
  // the inline style is harmless within it.
  pre: ({ children }: { children?: ReactNode }) => (
    <pre className="mb-2 overflow-x-auto rounded border border-border bg-sunken p-2 text-[11px] last:mb-0">
      {children}
    </pre>
  ),
  blockquote: ({ children }: { children?: ReactNode }) => (
    <blockquote className="mb-2 border-l-2 border-border pl-2 text-ink-muted last:mb-0">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-2 border-border" />,
  a: SafeLink,
  // A table in a 460px column overflows whatever its content is, so it scrolls in its own box rather than
  // widening the bubble. The system prompt asks the model not to write them; this is what happens anyway.
  table: ({ children }: { children?: ReactNode }) => (
    <div className="mb-2 overflow-x-auto last:mb-0">
      <table className="w-full border-collapse text-[11px]">{children}</table>
    </div>
  ),
  th: ({ children }: { children?: ReactNode }) => (
    <th className="border border-border px-1.5 py-0.5 text-left font-semibold text-ink">
      {children}
    </th>
  ),
  td: ({ children }: { children?: ReactNode }) => (
    <td className="border border-border px-1.5 py-0.5">{children}</td>
  ),
};

function Heading({ children }: { children?: ReactNode }) {
  return <p className="mb-1 font-semibold text-ink last:mb-0">{children}</p>;
}

/** Anything that is not http(s) is shown as text, not as something to click. A model writing `javascript:`
 *  or `data:` is the one remaining way its output could act on the operator rather than inform them. */
function SafeLink({ href, children }: { href?: string; children?: ReactNode }) {
  const safe = href !== undefined && /^https?:\/\//i.test(href);
  if (!safe) return <span className="text-ink">{children}</span>;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-secondary underline underline-offset-2 hover:text-ink"
    >
      {children}
    </a>
  );
}

export function MessageBody({ text, streaming = false }: { text: string; streaming?: boolean }) {
  const source = streaming ? remend(text, REMEND_OPTIONS) : text;
  return (
    <Markdown remarkPlugins={[remarkGfm]} components={COMPONENTS}>
      {source}
    </Markdown>
  );
}
