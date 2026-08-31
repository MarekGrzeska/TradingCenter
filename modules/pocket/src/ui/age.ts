/** `"4 min ago"` — how long ago something happened, coarse. Shared by both screens: the archive ticks in
 *  minutes, so seconds would be noise that changes on every render, and a wall-clock time on a phone is
 *  one more thing to convert. `null` is "never", which a price with no moment and an archive that has
 *  never answered both are. */
export function formatAge(moment: Date | null, now: Date = new Date()): string {
  if (moment === null) return "never";
  const seconds = Math.max(0, Math.round((now.getTime() - moment.getTime()) / 1000));
  if (seconds < 90) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}
