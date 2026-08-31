import type { ReactNode } from "react";
import styles from "./Pill.module.css";

export type PillTone = "ok" | "warn" | "muted";

const toneClass: Record<PillTone, string> = {
  ok: styles.ok,
  warn: styles.warn,
  muted: styles.muted,
};

export function Pill({ tone, children }: { tone: PillTone; children: ReactNode }) {
  return <span className={[styles.pill, toneClass[tone]].join(" ")}>{children}</span>;
}
