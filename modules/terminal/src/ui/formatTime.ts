import { TickMarkType } from "lightweight-charts";

/**
 * Every date the terminal shows is converted to this zone; the wire and the internal representation stay UTC epoch
 * seconds throughout. A terminal opened from any browser timezone shows the same wall-clock time as one in Poland.
 */
const TIME_ZONE = "Europe/Warsaw";

/**
 * `en-GB`, not `pl-PL`: with `timeZoneName: "short"` it gives the abbreviation that tracks daylight saving. `pl-PL`
 * collapses both onto `CET` year-round, which makes a summer instant look an hour off to anyone trusting the label.
 */
const ZONE_LOCALE = "en-GB";

function partsOf(formatter: Intl.DateTimeFormat, epochMs: number) {
  const found = new Map(formatter.formatToParts(epochMs).map((p) => [p.type, p.value]));
  return (type: Intl.DateTimeFormatPartTypes) => found.get(type) ?? "";
}

// `timeZoneName` does not combine with `dateStyle`/`timeStyle` — `Intl.DateTimeFormat`
// throws `Invalid option` at construction time — so every field is spelled out.
const INSTANT_FORMAT = new Intl.DateTimeFormat(ZONE_LOCALE, {
  timeZone: TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  timeZoneName: "short",
});

/** `2026-08-10 16:10 CEST` — the one shape every instant in the terminal is shown in. */
export function formatInstant(epochSeconds: number): string {
  const part = partsOf(INSTANT_FORMAT, epochSeconds * 1000);
  return `${part("year")}-${part("month")}-${part("day")} ${part("hour")}:${part("minute")} ${part("timeZoneName")}`;
}

/** Whether the browser is somewhere other than the zone every time here is shown in.
 *  Read once, at module load: a browser does not move zone mid-session, and a schedule
 *  panel asking per render would ask hundreds of times for one answer. */
const BROWSER_ZONE = Intl.DateTimeFormat().resolvedOptions().timeZone;

export function browserIsInScheduleZone(): boolean {
  return BROWSER_ZONE === TIME_ZONE;
}

const BROWSER_FORMAT = new Intl.DateTimeFormat(ZONE_LOCALE, {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  timeZoneName: "short",
});

/** The same second in whatever zone the browser is in — shown *beside* `formatInstant`,
 *  and only for an operator outside Polish time (specs/terminal-teams-schedules, "Czas
 *  jest pokazany tak, żeby nie trzeba było go przeliczać"). */
export function formatBrowserInstant(epochSeconds: number): string {
  const part = partsOf(BROWSER_FORMAT, epochSeconds * 1000);
  return `${part("year")}-${part("month")}-${part("day")} ${part("hour")}:${part("minute")} ${part("timeZoneName")}`;
}

/** An approximation, same as the number it describes (`market-data-jobs`
 *  spec, "Zlecenie da się wycenić przed jego uruchomieniem") — one decimal is
 *  enough precision for a number the operator is not meant to trust exactly. */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// `lightweight-charts` draws its time axis in UTC and knows nothing of a viewer's zone; these two formatters are how
// it learns Warsaw's. The candles' own timestamps are never touched — only how the axis labels them.

const CROSSHAIR_FORMAT = new Intl.DateTimeFormat(ZONE_LOCALE, {
  timeZone: TIME_ZONE,
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

/** The crosshair's own time label (`localization.timeFormatter`) — fuller than a tick
 *  mark, because it stands alone rather than next to its neighbours on the axis. */
export function formatCrosshairTime(epochSeconds: number): string {
  const part = partsOf(CROSSHAIR_FORMAT, epochSeconds * 1000);
  return `${part("day")} ${part("month")} ${part("year")} ${part("hour")}:${part("minute")}`;
}

const TICK_YEAR_FORMAT = new Intl.DateTimeFormat(ZONE_LOCALE, {
  timeZone: TIME_ZONE,
  year: "numeric",
});
const TICK_MONTH_DAY_FORMAT = new Intl.DateTimeFormat(ZONE_LOCALE, {
  timeZone: TIME_ZONE,
  month: "short",
  day: "2-digit",
});
const TICK_TIME_FORMAT = new Intl.DateTimeFormat(ZONE_LOCALE, {
  timeZone: TIME_ZONE,
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

/** Axis tick marks (`timeScale.tickMarkFormatter`). The library asks per tick what
 *  grain it wants — year, month, day, time — and Warsaw's calendar answers instead of
 *  UTC's, which is what actually moves a tick across the date the two zones disagree
 *  on. Kept under the library's own 8-character budget for a tick label. */
export function formatTickMark(epochSeconds: number, tickMarkType: TickMarkType): string {
  const epochMs = epochSeconds * 1000;
  switch (tickMarkType) {
    case TickMarkType.Year:
      return TICK_YEAR_FORMAT.format(epochMs);
    case TickMarkType.Month:
    case TickMarkType.DayOfMonth:
      return TICK_MONTH_DAY_FORMAT.format(epochMs);
    default:
      return TICK_TIME_FORMAT.format(epochMs);
  }
}

const DATE_INPUT_FORMAT = new Intl.DateTimeFormat("en-CA", {
  timeZone: TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

/** Today's date, as a Warsaw calendar day in `<input type="date">`'s own
 *  `YYYY-MM-DD` shape — `en-CA` is the one built-in locale that formats a date
 *  that way, which is incidental to Canada and load-bearing here. */
export function todayInWarsaw(): string {
  return DATE_INPUT_FORMAT.format(Date.now());
}

/** The Warsaw offset in effect at a given UTC instant, in minutes east of UTC —
 *  derived from `Intl`'s own tables rather than a fixed number, so it tracks the
 *  daylight-saving transition without maintaining one. */
function warsawOffsetMinutesAt(epochMs: number): number {
  const parts = partsOf(
    new Intl.DateTimeFormat("en-US", {
      timeZone: TIME_ZONE,
      hour12: false,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }),
    epochMs,
  );
  // `Intl` spells midnight "24" rather than "00" in this locale's 24-hour output.
  const hour = part24(parts("hour"));
  const asUtc = Date.UTC(
    Number(parts("year")),
    Number(parts("month")) - 1,
    Number(parts("day")),
    hour,
    Number(parts("minute")),
    Number(parts("second")),
  );
  return (asUtc - epochMs) / 60_000;
}

function part24(hour: string): number {
  return hour === "24" ? 0 : Number(hour);
}

/** A Warsaw calendar day to the epoch second of its midnight in Warsaw, which is what "Data podana przez operatora"
 *  means. Europe's transitions land at 01:00 UTC, safely after either midnight, so the UTC guess is never wrong. */
export function warsawMidnightEpochSeconds(dateInput: string): number {
  const utcGuessMs = Date.parse(`${dateInput}T00:00:00Z`);
  const offsetMinutes = warsawOffsetMinutesAt(utcGuessMs);
  return Math.floor((utcGuessMs - offsetMinutes * 60_000) / 1000);
}
