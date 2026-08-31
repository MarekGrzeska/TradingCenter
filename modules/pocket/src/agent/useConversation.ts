import { useCallback, useEffect, useRef, useState } from "react";
import type { AgentApi, AgentMessage, AgentModel, AgentSession, AgentToolCall } from "./agentApi";

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
  /** Every conversation this operator has, newest first — the module orders them by last activity. */
  sessions: AgentSession[];
  /** The one on screen, or `null` for a new conversation nobody has written to yet. It has no id
   *  until the first message: a session created on opening the tab is an empty row in this list. */
  sessionId: number | null;
  /** The first read, which has nothing on screen to keep if it fails. */
  loading: boolean;
  error: string | null;
  send: (content: string) => void;
  stop: () => void;
  open: (sessionId: number) => void;
  startNew: () => void;
  chooseModel: (modelId: string) => void;
  dismissError: () => void;
}

function messageOf(cause: unknown): string {
  return cause instanceof Error ? cause.message : "the workbench could not be reached";
}

/**
 * The conversations, resumed rather than started: the newest is picked up on open, and a new one is
 * created on its first message only. A session created every time the tab is opened is a list of
 * empty conversations the operator scrolls past to find the one they meant.
 */
export function useConversation(api: AgentApi): Conversation {
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [streaming, setStreaming] = useState<Streaming | null>(null);
  const [models, setModels] = useState<AgentModel[]>([]);
  const [sessions, setSessions] = useState<AgentSession[]>([]);
  const [modelId, setModelId] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // The turn in flight, so stopping and unmounting both have something to end. A second send while
  // one is running is refused by the composer.
  const turn = useRef<AbortController | null>(null);
  // What the turn writes to, read by the send that started it. State would be a render behind.
  const current = useRef<number | null>(null);

  const remember = useCallback((id: number | null) => {
    current.current = id;
    setSessionId(id);
  }, []);

  useEffect(() => {
    const controller = new AbortController();

    void (async () => {
      try {
        const [catalogue, list] = await Promise.all([
          api.listModels(controller.signal),
          api.listSessions(controller.signal),
        ]);
        if (controller.signal.aborted) return;
        setModels(catalogue);
        setSessions(list);

        const newest = list[0];
        if (newest !== undefined) {
          remember(newest.id);
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
  }, [api, remember]);

  const open = useCallback(
    (id: number) => {
      if (id === current.current) return;
      remember(id);
      setMessages([]);
      setStreaming(null);
      setModelId(sessions.find((session) => session.id === id)?.currentModelId ?? null);

      const controller = new AbortController();
      void (async () => {
        try {
          setMessages(await api.listMessages(id, controller.signal));
        } catch (cause) {
          setError(messageOf(cause));
        }
      })();
    },
    [api, remember, sessions],
  );

  /** Nothing is created here. The conversation exists once it is written to, which is what keeps the
   *  history free of rows nobody said anything in. */
  const startNew = useCallback(() => {
    remember(null);
    setMessages([]);
    setStreaming(null);
    setError(null);
  }, [remember]);

  const send = useCallback(
    (content: string) => {
      if (turn.current !== null) return;
      const controller = new AbortController();
      turn.current = controller;
      setError(null);

      void (async () => {
        try {
          if (current.current === null) {
            const session = await api.createSession(modelId, controller.signal);
            remember(session.id);
            setModelId(session.currentModelId);
          }
          const id = current.current as number;

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
          // And the list, because a conversation's title and its place in it are the module's: this
          // one was just written to, and on a first message it did not exist here at all.
          setSessions(await api.listSessions(controller.signal));
        } catch (cause) {
          if (!controller.signal.aborted) setError(messageOf(cause));
        } finally {
          setStreaming(null);
          turn.current = null;
        }
      })();
    },
    [api, modelId, remember],
  );

  const stop = useCallback(() => {
    const id = current.current;
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
      const id = current.current;
      // A conversation that does not exist yet is created with this model rather than patched: there
      // is nothing to patch, and `createSession` already takes it.
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
    sessions,
    sessionId,
    loading,
    error,
    send,
    stop,
    open,
    startNew,
    chooseModel,
    dismissError: () => setError(null),
  };
}
