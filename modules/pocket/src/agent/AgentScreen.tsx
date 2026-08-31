import { useEffect, useRef, useState } from "react";
import type { AgentApi } from "./agentApi";
import { useConversation } from "./useConversation";
import { ToolCallChip } from "./ToolCallChip";
import { Button } from "../ui/Button";
import styles from "./AgentScreen.module.css";

/** How tall the composer is allowed to grow before it scrolls instead. Five lines: past that the
 *  message is longer than the reply it will get, and the transcript has stopped being visible. */
const MAX_COMPOSER_ROWS = 5;

export function AgentScreen({ api }: { api: AgentApi }) {
  const conversation = useConversation(api);
  const [draft, setDraft] = useState("");
  const composer = useRef<HTMLTextAreaElement>(null);
  const foot = useRef<HTMLDivElement>(null);

  const streaming = conversation.streaming !== null;

  // The newest line, kept in view as it grows. `block: "end"` rather than a scrollTop sum: the
  // composer's own height changes under it, and a computed offset is wrong the moment it does.
  useEffect(() => {
    foot.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [conversation.messages, conversation.streaming]);

  const submit = () => {
    const content = draft.trim();
    if (content === "" || streaming) return;
    conversation.send(content);
    setDraft("");
    if (composer.current) composer.current.style.height = "auto";
  };

  return (
    <div className={styles.screen}>
      <header className={styles.header}>
        <h1 className={styles.heading}>Agent</h1>
        {conversation.models.length === 0 ? null : (
          <select
            className={styles.model}
            aria-label="Model"
            value={conversation.modelId ?? ""}
            onChange={(event) => conversation.chooseModel(event.target.value)}
          >
            {conversation.modelId === null ? <option value="">default</option> : null}
            {conversation.models.map((model) => (
              <option key={model.id} value={model.id}>
                {model.displayName}
              </option>
            ))}
          </select>
        )}
      </header>

      <div className={styles.transcript}>
        {conversation.error === null ? null : (
          <p className={styles.error} role="alert" onClick={conversation.dismissError}>
            {conversation.error}
          </p>
        )}

        {conversation.loading ? (
          <p className={styles.state} role="status">
            Reading the conversation…
          </p>
        ) : conversation.messages.length === 0 && !streaming ? (
          <p className={styles.state}>
            Ask about a tracked market, or about one that is not tracked yet — the agent reads the
            archive through its own tools and says which it used.
          </p>
        ) : null}

        {conversation.messages.map((message) => (
          <article
            key={message.id}
            className={message.role === "operator" ? styles.fromOperator : styles.fromAgent}
          >
            <p className={styles.text}>{message.content}</p>
            {message.toolCalls.length === 0 ? null : (
              <ul className={styles.calls}>
                {message.toolCalls.map((call) => (
                  <ToolCallChip key={`${call.roundIndex}-${call.position}`} call={call} />
                ))}
              </ul>
            )}
            {!message.incomplete ? null : (
              <p className={styles.incomplete}>
                {message.stopped ? "you stopped this turn" : "this turn did not finish"}
              </p>
            )}
          </article>
        ))}

        {conversation.streaming === null ? null : (
          <article className={styles.fromAgent}>
            {conversation.streaming.toolCalls.length === 0 ? null : (
              <ul className={styles.calls}>
                {conversation.streaming.toolCalls.map((call) => (
                  <ToolCallChip key={`live-${call.roundIndex}-${call.position}`} call={call} />
                ))}
              </ul>
            )}
            <p className={styles.text}>
              {conversation.streaming.text}
              <span className={styles.caret} aria-label="the agent is answering" />
            </p>
          </article>
        )}

        <div ref={foot} />
      </div>

      <div className={styles.composer}>
        <textarea
          ref={composer}
          className={styles.input}
          rows={1}
          placeholder="Ask the agent"
          value={draft}
          disabled={streaming}
          onChange={(event) => {
            setDraft(event.target.value);
            // Grown to fit, capped, then allowed to scroll. Measured from `auto` each time, because
            // a textarea's scrollHeight never shrinks on its own.
            const field = event.currentTarget;
            field.style.height = "auto";
            const rowHeight = parseFloat(getComputedStyle(field).lineHeight) || 20;
            field.style.height = `${Math.min(field.scrollHeight, rowHeight * MAX_COMPOSER_ROWS + 20)}px`;
          }}
          onKeyDown={(event) => {
            // Enter sends only with a keyboard attached. On a phone Enter is a newline — a send key
            // where the newline key belongs sends half-written questions.
            if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
              event.preventDefault();
              submit();
            }
          }}
        />
        {streaming ? (
          <Button tone="secondary" onClick={conversation.stop}>
            Stop
          </Button>
        ) : (
          <Button tone="primary" onClick={submit} disabled={draft.trim() === ""}>
            Send
          </Button>
        )}
      </div>
    </div>
  );
}
