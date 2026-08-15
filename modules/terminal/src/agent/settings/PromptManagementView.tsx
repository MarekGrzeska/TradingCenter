import { useEffect, useState } from "react";
import { agentApi, type AgentApi, type AgentPrompt } from "../agentApi";
import { usePrompt } from "./usePrompt";

interface Draft {
  withTools: string;
  withoutTools: string;
}

function draftOf(prompt: AgentPrompt): Draft {
  return { withTools: prompt.withTools, withoutTools: prompt.withoutTools };
}

/**
 * View and edit the system prompt the agent actually runs, from the terminal instead
 * of a commit and a deploy (`terminal-agent-prompt-management` spec). `current` is
 * only ever set from a response the module sent — never from what the operator is
 * mid-typing, so a refused save leaves the last confirmed version on screen rather
 * than something that looks saved but is not.
 */
export function PromptManagementView({ api = agentApi }: { api?: AgentApi } = {}) {
  const state = usePrompt(api);
  const [current, setCurrent] = useState<AgentPrompt | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (state.status === "ready" && state.prompt) {
      setCurrent(state.prompt);
      setDraft(draftOf(state.prompt));
    }
  }, [state.status, state.prompt]);

  async function save() {
    if (!draft) return;
    setSaving(true);
    setSaveError(null);
    try {
      const updated = await api.updatePrompt(
        draft.withTools,
        draft.withoutTools,
        new AbortController().signal,
      );
      setCurrent(updated);
      setDraft(draftOf(updated));
    } catch (cause) {
      setSaveError(cause instanceof Error ? cause.message : "could not save the prompt");
    } finally {
      setSaving(false);
    }
  }

  if (state.status === "loading" && !current) {
    return <p className="text-sm text-ink-muted">Reading the prompt…</p>;
  }

  if (state.status === "unreachable" && !current) {
    return (
      <p className="text-sm text-critical">
        the agent module is not reachable, so the prompt is unknown — this is not
        empty. {state.error}
        <button
          type="button"
          onClick={state.reload}
          className="ml-3 rounded border border-border px-2 py-0.5 text-xs text-ink hover:bg-panel-strong"
        >
          Retry
        </button>
      </p>
    );
  }

  if (!current || !draft) return null; // "ready" (or already loaded once) always carries one

  const dirty = draft.withTools !== current.withTools || draft.withoutTools !== current.withoutTools;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3 text-xs text-ink-muted">
        <span>
          Version <span className="font-semibold text-ink">{current.version}</span>
        </span>
      </div>

      <PromptField
        id="prompt-with-tools"
        label="With tools"
        value={draft.withTools}
        onChange={(withTools) => setDraft({ ...draft, withTools })}
      />
      <PromptField
        id="prompt-without-tools"
        label="Without tools"
        value={draft.withoutTools}
        onChange={(withoutTools) => setDraft({ ...draft, withoutTools })}
      />

      {saveError && <p className="text-sm text-critical">{saveError}</p>}

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={save}
          disabled={saving || !dirty}
          className="cursor-pointer rounded border border-primary-line bg-primary-soft px-3 py-1 text-sm text-ink hover:bg-primary-strong hover:text-ink-inverse disabled:cursor-not-allowed disabled:opacity-40"
        >
          {saving ? "Saving…" : "Save"}
        </button>
        {dirty && !saving && <span className="text-xs text-ink-faint">unsaved changes</span>}
      </div>
    </div>
  );
}

function PromptField({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-xs font-semibold uppercase tracking-wide text-secondary">
        {label}
      </label>
      <textarea
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        rows={10}
        className="w-full rounded border border-border bg-sunken px-2 py-1.5 text-sm text-ink"
      />
    </div>
  );
}
