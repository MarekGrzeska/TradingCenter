import type { ButtonHTMLAttributes, ReactNode } from "react";

/**
 * Four tones and four sizes, which is every button this terminal has. It exists because the same class string was
 * pasted sixty times and drifted — `className` is for where a button *sits*, never for how it looks.
 */
export type ButtonTone = "quiet" | "muted" | "primary" | "critical";
export type ButtonSize = "2xs" | "xs" | "sm" | "md";

const TONES: Record<ButtonTone, string> = {
  quiet: "border-border text-ink hover:bg-panel-strong",
  // Dimmer until pointed at — a secondary action beside the one the operator came for. The distinction was already
  // in the views: eight buttons were written `text-ink-muted hover:text-ink`, following what the button was for.
  muted: "border-border text-ink-muted hover:bg-panel-strong hover:text-ink",
  primary:
    "border-primary-line bg-primary-soft text-ink hover:bg-primary-strong hover:text-ink-inverse",
  // The one tone about consequence rather than emphasis. Bordered rather than filled, because a red field reads as
  // a warning about the state the operator is in, and this is a thing they may do.
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
