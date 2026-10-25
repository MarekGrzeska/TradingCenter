import { useEffect, useRef, useState } from "react";
import { messageOf } from "../data/query";
import type { Checked } from "./StrategyEditor";
import type { StrategiesApi, Summary } from "./strategiesApi";

/** A pause in typing this long asks the package; shorter, every few letters would be a request. */
export const PAUSE_MS = 600;

export interface LiveValidation {
  /** What the package said, with the text it said it about. */
  checked: Checked | null;
  valid: boolean | null;
  summary: Summary | null;
  /** True while the text on screen is not the one last checked. */
  stale: boolean;
  failure: string | null;
}

/**
 * Asks the package about the editor's text after a pause — never for text it already asked about, never while the
 * terminal is not on screen, and never for text that is not JSON yet (the editor says that itself, without asking).
 */
export function useLiveValidation(api: StrategiesApi, text: string, enabled: boolean): LiveValidation {
  const [result, setResult] = useState<{ text: string; valid: boolean; checked: Checked; summary: Summary | null } | null>(
    null,
  );
  const [failure, setFailure] = useState<string | null>(null);
  const [visible, setVisible] = useState(() => document.visibilityState !== "hidden");
  const asked = useRef<string | null>(null);

  useEffect(() => {
    const onChange = () => setVisible(document.visibilityState !== "hidden");
    document.addEventListener("visibilitychange", onChange);
    return () => document.removeEventListener("visibilitychange", onChange);
  }, []);

  useEffect(() => {
    if (!enabled || !visible || asked.current === text) return;
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      void api
        .validate(parsed, controller.signal)
        .then((answer) => {
          asked.current = text;
          setFailure(null);
          setResult({ text, valid: answer.valid, checked: { text, problems: answer.problems }, summary: answer.summary });
        })
        .catch((cause: unknown) => {
          if (!controller.signal.aborted) setFailure(messageOf(cause, "nie udało się sprawdzić dokumentu"));
        });
    }, PAUSE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [api, text, enabled, visible]);

  const current = result !== null && result.text === text;
  return {
    checked: result?.checked ?? null,
    valid: current ? result.valid : null,
    summary: result?.summary ?? null,
    stale: !current,
    failure,
  };
}
