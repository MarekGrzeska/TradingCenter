import { useEffect, useRef, useState } from "react";
import type { AgentApi } from "./agentApi";
import { useConversation } from "./useConversation";
import { ToolCallChip } from "./ToolCallChip";
import { SessionsSheet } from "./SessionsSheet";
import { Button } from "../ui/Button";
import styles from "./AgentScreen.module.css";

/** How tall the composer is allowed to grow before it scrolls instead. Five lines: past that the
 *  message is longer than the reply it will get, and the transcript has stopped being visible. */
const MAX_COMPOSER_ROWS = 5;

export function AgentScreen({ api }: { api: AgentApi }) {
  const conversation = useConversation(api);
  const [draft, setDraft] = useState("");
  const [picking, setPicking] = useState(false);
  const composer = useRef<HTMLTextAreaElement>(null);
  const foot = useRef<HTMLDivElement>(null);

  const streaming = conversation.streaming !== null;
  const title =
    conversation.sessions.find((session) => session.id === conversation.sessionId)?.title?.trim() ||
    (conversation.sessionId === null ? "New conversation" : "This conversation");

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
        {/* The title is the picker. A phone header holds two things; a heading that only says
            "Agent" would spend one of them saying what the tab bar already says. */}
        <button
          type="button"
          className={styles.picker}
          aria-label="Conversations"
          aria-haspopup="dialog"
          onClick={() => setPicking(true)}
        >
          <span className={styles.pickerTitle}>{title}</span>
          <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden>
            <path
              d="M2.5 4.5 6 8 9.5 4.5"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>

        <button
          type="button"
          className={styles.new}
          aria-label="New conversation"
          onClick={() => {
            conversation.startNew();
            setDraft("");
          }}
        >
          <svg viewBox="0 0 20 20" width="20" height="20" aria-hidden>
            <path
              d="M10 4v12M4 10h12"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
            />
          </svg>
        </button>
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

      {!picking ? null : (
        <SessionsSheet
          sessions={conversation.sessions}
          current={conversation.sessionId}
          models={conversation.models}
          modelId={conversation.modelId}
          onOpen={(id) => {
            conversation.open(id);
            setPicking(false);
          }}
          onNew={() => {
            conversation.startNew();
            setDraft("");
            setPicking(false);
          }}
          onChooseModel={conversation.chooseModel}
          onClose={() => setPicking(false)}
        />
      )}
    </div>
  );
}
