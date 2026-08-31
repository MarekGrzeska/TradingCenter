import { useState } from "react";
import type { AgentToolCall } from "./agentApi";
import styles from "./ToolCallChip.module.css";

const OUTCOME_CLASS = {
  ok: styles.ok,
  refused: styles.refused,
  unavailable: styles.unavailable,
  unknown: styles.unknown,
  unrecognised: styles.unknown,
} as const;

/** What the agent actually did, not a claim that it did something. Collapsed it is one line a thumb
 *  can pass over; opened it is the arguments and the text the model itself was handed — which is the
 *  only way to tell a tool that answered nothing from one that was never asked. */
export function ToolCallChip({ call }: { call: AgentToolCall }) {
  const [open, setOpen] = useState(false);

  return (
    <li className={styles.item}>
      <button
        type="button"
        className={styles.head}
        aria-expanded={open}
        onClick={() => setOpen((previous) => !previous)}
      >
        <span className={[styles.dot, OUTCOME_CLASS[call.outcome]].join(" ")} aria-hidden />
        <span className={styles.name}>{call.name}</span>
        <span className={styles.outcome}>{call.outcome}</span>
        <span className={styles.duration}>{Math.round(call.durationMs)} ms</span>
      </button>

      {!open ? null : (
        <div className={styles.body}>
          <p className={styles.label}>Arguments</p>
          <pre className={styles.pre}>{JSON.stringify(call.arguments, null, 2)}</pre>
          <p className={styles.label}>What the model was handed</p>
          <pre className={styles.pre}>{call.resultText}</pre>
        </div>
      )}
    </li>
  );
}
