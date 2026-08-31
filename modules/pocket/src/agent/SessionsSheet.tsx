import type { AgentModel, AgentSession } from "./agentApi";
import { Sheet } from "../ui/Sheet";
import { Button } from "../ui/Button";
import styles from "./SessionsSheet.module.css";

export interface SessionsSheetProps {
  sessions: AgentSession[];
  current: number | null;
  models: AgentModel[];
  modelId: string | null;
  onOpen: (sessionId: number) => void;
  onNew: () => void;
  onChooseModel: (modelId: string) => void;
  onClose: () => void;
}

/** A conversation with no first message has no title yet — the module titles one from what was said
 *  in it, so an untitled row is a conversation, not a bug. */
function titleOf(session: AgentSession): string {
  const title = session.title?.trim();
  return title ? title : `Conversation ${session.id}`;
}

/** Relative for the recent ones and a date for the rest: "3 days ago" stops being an answer about
 *  the week before last, and a phone list is scanned rather than read. */
function whenOf(session: AgentSession, now: Date): string {
  const hours = (now.getTime() - session.lastActiveAt.getTime()) / 3_600_000;
  if (hours < 1) return "just now";
  if (hours < 24) return `${Math.round(hours)} h ago`;
  if (hours < 72) return `${Math.round(hours / 24)} d ago`;
  return session.lastActiveAt.toLocaleDateString();
}

export function SessionsSheet({
  sessions,
  current,
  models,
  modelId,
  onOpen,
  onNew,
  onChooseModel,
  onClose,
}: SessionsSheetProps) {
  const now = new Date();

  return (
    <Sheet
      title="Conversations"
      onClose={onClose}
      actions={
        <>
          <Button onClick={onClose}>Close</Button>
          <Button tone="primary" onClick={onNew}>
            New conversation
          </Button>
        </>
      }
    >
      {models.length === 0 ? null : (
        <div className={styles.field}>
          <label className={styles.label} htmlFor="agent-model">
            Model
          </label>
          <select
            id="agent-model"
            className={styles.select}
            value={modelId ?? ""}
            onChange={(event) => onChooseModel(event.target.value)}
          >
            {modelId === null ? <option value="">the workbench&apos;s default</option> : null}
            {models.map((model) => (
              <option key={model.id} value={model.id}>
                {model.displayName}
              </option>
            ))}
          </select>
        </div>
      )}

      {sessions.length === 0 ? (
        <p className={styles.empty}>
          Nothing here yet. A conversation appears once something has been said in it.
        </p>
      ) : (
        <ul className={styles.list}>
          {sessions.map((session) => (
            <li key={session.id}>
              <button
                type="button"
                className={session.id === current ? styles.current : styles.row}
                aria-current={session.id === current ? "true" : undefined}
                onClick={() => onOpen(session.id)}
              >
                <span className={styles.title}>{titleOf(session)}</span>
                <span className={styles.when}>{whenOf(session, now)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Sheet>
  );
}
