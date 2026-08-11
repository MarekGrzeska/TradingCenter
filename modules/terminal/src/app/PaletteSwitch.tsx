import { useEffect, useState } from "react";

/**
 * Testing scaffolding, not a feature: two candidate palettes are declared in `index.css`
 * and this flips `data-palette` on the root between them. Delete it — and the second block
 * in the stylesheet — the moment one of them is chosen.
 */

const PALETTES = [
  { id: "amber", label: "Amber" },
  { id: "copper", label: "Copper" },
] as const;

type PaletteId = (typeof PALETTES)[number]["id"];

const STORAGE_KEY = "terminal.palette.testing";

function stored(): PaletteId {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "copper" ? "copper" : "amber";
  } catch {
    return "amber";
  }
}

export function PaletteSwitch() {
  const [palette, setPalette] = useState<PaletteId>(stored);

  useEffect(() => {
    document.documentElement.dataset.palette = palette;
    try {
      window.localStorage.setItem(STORAGE_KEY, palette);
    } catch {
      // Nothing to do — the choice just won't outlive the reload.
    }
  }, [palette]);

  return (
    <div className="flex items-center gap-1 rounded border border-border p-0.5" role="group" aria-label="Palette (testing)">
      {PALETTES.map((entry) => (
        <button
          key={entry.id}
          type="button"
          aria-pressed={palette === entry.id}
          onClick={() => setPalette(entry.id)}
          className={`cursor-pointer rounded px-2 py-0.5 text-xs transition-colors ${
            palette === entry.id
              ? "bg-primary-soft text-primary"
              : "text-ink-muted hover:text-ink"
          }`}
        >
          {entry.label}
        </button>
      ))}
    </div>
  );
}
