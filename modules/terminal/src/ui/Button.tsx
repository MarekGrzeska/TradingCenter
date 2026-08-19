import type { ButtonHTMLAttributes, ReactNode } from "react";

/**
 * The terminal's own button.
 *
 * Not a design system — four tones and four sizes, which is every button this terminal
 * actually has. It exists because the same class string was written out verbatim eight
 * times for the retry beside a failure and four more for the quiet action in a panel
 * header, and copies drift: half of them carried `cursor-pointer` and half did not, so
 * the pointer changed shape depending on which view the operator was in.
 *
 * The second pass through the views found fifty more, and the drift in them was worse
 * than the first batch's: the same primary action was written with `border-primary-line`
 * in four places and `border-primary` in three, disabled meant `opacity-40` here and
 * `opacity-50` there and nothing at all somewhere else, and eight quiet buttons carried
 * `px-1.5` with no vertical padding at all — a different height from their neighbours
 * for no reason anybody chose.
 *
 * `className` is for where a button *sits* — a margin, `ml-auto`, `self-start` — never
 * for how it looks. Anything else belongs in a tone or a size here, so that the next one
 * is a choice rather than a paste.
 */
export type ButtonTone = "quiet" | "muted" | "primary" | "critical";
export type ButtonSize = "2xs" | "xs" | "sm" | "md";

const TONES: Record<ButtonTone, string> = {
  quiet: "border-border text-ink hover:bg-panel-strong",
  // Dimmer until pointed at — a secondary action sitting beside the one the operator
  // came for. The distinction is real and was already in the views: most bordered
  // buttons were written `text-ink`, and eight `text-ink-muted hover:text-ink`, and the
  // split followed what the button was for rather than who wrote it.
  muted: "border-border text-ink-muted hover:bg-panel-strong hover:text-ink",
  primary:
    "border-primary-line bg-primary-soft text-ink hover:bg-primary-strong hover:text-ink-inverse",
  // The one tone that is about consequence rather than emphasis: cancelling a run,
  // removing an agent. Bordered rather than filled, because a red field reads as a
  // warning about the state the operator is in, and this is a thing they may do.
  critical: "border-critical text-critical hover:bg-panel-strong",
};

const SIZES: Record<ButtonSize, string> = {
  "2xs": "px-1.5 py-0.5 text-[10px]",
  xs: "px-2 py-0.5 text-xs",
  sm: "px-2 py-1 text-xs",
  md: "px-3 py-1 text-sm",
};

export function Button({
  tone = "quiet",
  size = "sm",
  className,
  children,
  ...rest
}: {
  tone?: ButtonTone;
  size?: ButtonSize;
  children: ReactNode;
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      {...rest}
      className={[
        "cursor-pointer rounded border transition-colors disabled:cursor-not-allowed disabled:opacity-40",
        TONES[tone],
        SIZES[size],
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {children}
    </button>
  );
}
