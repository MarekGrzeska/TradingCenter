import type { ButtonHTMLAttributes } from "react";
import styles from "./Button.module.css";

export type ButtonTone = "primary" | "secondary" | "danger";

const toneClass: Record<ButtonTone, string> = {
  primary: styles.primary,
  secondary: styles.secondary,
  danger: styles.danger,
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  tone?: ButtonTone;
}

export function Button({ tone = "secondary", className, type, ...rest }: ButtonProps) {
  return (
    <button
      // Explicit, because a button inside the track sheet's form would otherwise submit it on the
      // way to cancelling.
      type={type ?? "button"}
      className={[styles.button, toneClass[tone], className].filter(Boolean).join(" ")}
      {...rest}
    />
  );
}
