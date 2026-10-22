import type { Prompt } from "./youtubeApi";

const INPUT = "rounded border border-border bg-sunken px-2 py-1 text-ink";

/**
 * A choice of prompt. `null` is "the seeded one", which is what the module takes when none is named — said in the first option
 * so nobody has to wonder what an empty choice does.
 */
export function PromptSelect({
  prompts,
  value,
  onChange,
  label,
  className = INPUT,
}: {
  prompts: Prompt[];
  value: number | null;
  onChange(promptId: number | null): void;
  label: string;
  className?: string;
}) {
  const seeded = prompts.find((prompt) => prompt.seeded);
  return (
    <select
      aria-label={label}
      className={className}
      value={value === null ? "" : String(value)}
      onChange={(event) => onChange(event.target.value === "" ? null : Number(event.target.value))}
    >
      <option value="">{seeded ? `domyślny (${seeded.name})` : "domyślny"}</option>
      {prompts
        .filter((prompt) => !prompt.seeded)
        .map((prompt) => (
          <option key={prompt.id} value={prompt.id}>
            {prompt.name}
          </option>
        ))}
    </select>
  );
}
