export const WINDOWS = [
  { minutes: 5, chip: "5m" },
  { minutes: 15, chip: "15m" },
  { minutes: 60, chip: "1h" },
  { minutes: 240, chip: "4h" },
  { minutes: 1440, chip: "24h" },
  { minutes: 10080, chip: "7d" },
] as const;

export const DEFAULT_MINUTES = 240;

/** "last 4 h", "last 7 d", "last 5 min" — the largest unit that divides the window evenly. */
export function windowLabel(minutes: number): string {
  if (minutes % 1440 === 0) return `last ${minutes / 1440} d`;
  if (minutes % 60 === 0) return `last ${minutes / 60} h`;
  return `last ${minutes} min`;
}

/** The server caps at 1000; a day or more of headlines is what needs the room. */
export function limitFor(minutes: number): number {
  return minutes >= 1440 ? 1000 : 300;
}
