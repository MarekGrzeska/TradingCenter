import type { ButtonHTMLAttributes, ReactNode } from "react";

/**
 * The terminal's own button.
 *
 * Not a design system — two sizes and two tones, which is every button this terminal
 * actually has. It exists because the same class string was written out verbatim eight
 * times for the retry beside a failure and four more for the quiet action in a panel
 * header, and copies drift: half of them carried `cursor-pointer` and half did not, so
 * the pointer changed shape depending on which view the operator was in.
 *
 * `className` is for where a button *sits* — a margin, `ml-auto`, `self-start` — never
 * for how it looks. Anything else belongs in a tone here, so that the next one is a
 * choice rather than a paste.
 */
export type ButtonTone = "quiet" | "primary";
export type ButtonSize = "xs" | "sm";

const TONES: Record<ButtonTone, string> = {
  quiet: "border-border text-ink hover:bg-panel-strong",
  primary:
    "border-primary-line bg-primary-soft text-ink hover:bg-primary-strong hover:text-ink-inverse",
};

const SIZES: Record<ButtonSize, string> = {
  xs: "px-2 py-0.5 text-xs",
  sm: "px-2 py-1 text-xs",
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
