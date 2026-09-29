/** The time windows the operator can look back over, and what each is called. */

export interface TimeWindow {
  minutes: number;
  label: string;
}

export const WINDOWS: readonly TimeWindow[] = [
  { minutes: 5, label: "5 min" },
  { minutes: 15, label: "15 min" },
  { minutes: 60, label: "1 h" },
  { minutes: 240, label: "4 h" },
  { minutes: 1440, label: "24 h" },
  { minutes: 10080, label: "7 d" },
];

export const DEFAULT_MINUTES = 240;

/** "ostatnie 4 h" — the window the list stands for, said rather than left to be inferred from the items. */
export function windowName(minutes: number): string {
  const known = WINDOWS.find((w) => w.minutes === minutes);
  return `ostatnie ${known?.label ?? `${minutes} min`}`;
}

/** How many headlines to ask for. A week holds far more than a day, and the server's ceiling is 1000. */
export function limitFor(minutes: number): number {
  return minutes >= 1440 ? 1000 : 300;
}
