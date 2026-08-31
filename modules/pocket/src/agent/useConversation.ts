import { useCallback, useEffect, useRef, useState } from "react";
import type { AgentApi, AgentMessage, AgentModel, AgentToolCall } from "./agentApi";

/** The reply as it is arriving: text so far and the calls the model has already made. It is not an
 *  `AgentMessage` — it has no id and is not in the transcript yet, and pretending otherwise is how a
 *  screen ends up showing a message twice. */
export interface Streaming {
  text: string;
  toolCalls: AgentToolCall[];
}

export interface Conversation {
  messages: AgentMessage[];
  streaming: Streaming | null;
  models: AgentModel[];
  modelId: string | null;
  /** The first read, which has nothing on screen to keep if it fails. */
  loading: boolean;
  error: string | null;
  send: (content: string) => void;
  stop: () => void;
  chooseModel: (modelId: string) => void;
  dismissError: () => void;
}

function messageOf(cause: unknown): string {
  return cause instanceof Error ? cause.message : "the workbench could not be reached";
}

/**
 * One conversation, resumed rather than started: the newest session is picked up on open, and a new
 * one is created on the first message only. A session created every time the tab is opened is a list
 * of empty conversations the operator has to scroll past to find the one they meant.
 */
export function useConversation(api: AgentApi): Conversation {
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [streaming, setStreaming] = useState<Streaming | null>(null);
  const [models, setModels] = useState<AgentModel[]>([]);
  const [modelId, setModelId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const sessionId = useRef<number | null>(null);
  // The turn in flight, so stopping and unmounting both have something to end. A second send while
  // one is running would replace the entry, which is why the composer refuses one.
  const turn = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    void (async () => {
      try {
        const [catalogue, sessions] = await Promise.all([
          api.listModels(controller.signal),
          api.listSessions(controller.signal),
        ]);
        if (controller.signal.aborted) return;
        setModels(catalogue);

        const newest = sessions[0];
        if (newest !== undefined) {
          sessionId.current = newest.id;
          setModelId(newest.currentModelId);
          setMessages(await api.listMessages(newest.id, controller.signal));
        }
        setLoading(false);
      } catch (cause) {
        if (controller.signal.aborted) return;
        setError(messageOf(cause));
        setLoading(false);
      }
    })();

    return () => controller.abort();
  }, [api]);

  const send = useCallback(
    (content: string) => {
      if (turn.current !== null) return;
      const controller = new AbortController();
      turn.current = controller;
      setError(null);

      void (async () => {
        try {
          if (sessionId.current === null) {
            const session = await api.createSession(modelId, controller.signal);
            sessionId.current = session.id;
            setModelId(session.currentModelId);
          }
          const id = sessionId.current;

          // Shown before the module has confirmed it, because the module stores it before the model
          // is ever called: what the operator typed survives a call that never answers.
          const pending: AgentMessage = {
            id: -Date.now(),
            role: "operator",
            content,
            incomplete: false,
            stopped: false,
            createdAt: new Date(),
            toolCalls: [],
          };
          setMessages((previous) => [...previous, pending]);
          setStreaming({ text: "", toolCalls: [] });

          const events = await api.sendMessage(id, content, controller.signal);
          for await (const event of events) {
            switch (event.kind) {
              case "fragment":
                setStreaming((previous) => ({
                  text: (previous?.text ?? "") + event.text,
                  toolCalls: previous?.toolCalls ?? [],
                }));
                break;
              case "toolCall":
                setStreaming((previous) => ({
                  text: previous?.text ?? "",
                  toolCalls: [...(previous?.toolCalls ?? []), event.call],
                }));
                break;
              case "error":
                setError(event.message);
                break;
              case "complete":
              case "stopped":
                break;
            }
          }

          // The transcript, not what was assembled here: it carries the ids, the tool calls as the
          // module recorded them, and whether the turn finished. A stopped turn keeps its partial
          // reply, so re-reading is also what makes stopping non-destructive.
          setMessages(await api.listMessages(id, controller.signal));
        } catch (cause) {
          if (!controller.signal.aborted) setError(messageOf(cause));
        } finally {
          setStreaming(null);
          turn.current = null;
        }
      })();
    },
    [api, modelId],
  );

  const stop = useCallback(() => {
    const id = sessionId.current;
    if (id === null || turn.current === null) return;
    // The module's stop, not the abort: aborting the request would leave the turn running with
    // nobody reading it, and the reply would be finished and billed with the screen none the wiser.
    void api.stop(id, new AbortController().signal).catch((cause: unknown) => {
      setError(messageOf(cause));
    });
  }, [api]);

  const chooseModel = useCallback(
    (next: string) => {
      setModelId(next);
      const id = sessionId.current;
      if (id === null) return;
      void api.setModel(id, next, new AbortController().signal).catch((cause: unknown) => {
        setError(messageOf(cause));
      });
    },
    [api],
  );

  useEffect(() => () => turn.current?.abort(), []);

  return {
    messages,
    streaming,
    models,
    modelId,
    loading,
    error,
    send,
    stop,
    chooseModel,
    dismissError: () => setError(null),
  };
}
