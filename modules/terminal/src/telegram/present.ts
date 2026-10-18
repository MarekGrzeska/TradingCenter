import type { Account, Bot, Destination, GateState } from "./telegramApi";

/** What the screen says, decided here so the decisions can be tested without a DOM. */

/** The destinations of one bot, in the order they were made (the door lists them that way). */
export function destinationsOf(bot: Bot, destinations: Destination[]): Destination[] {
  return destinations.filter((one) => one.bot === bot.username);
}

/** The name a recipient gets through this bot. The door keeps names unique across bots (a name is what an assignment and a
 *  message are addressed by), but one person may well receive through several bots — each a separate conversation that needs
 *  its own tap — so a name another bot already holds becomes `name-botname`, and a number if even that is taken. */
export function freeNameFor(wanted: string, bot: Bot, destinations: Destination[]): string {
  const name = wanted.trim();
  const holder = (candidate: string) => destinations.find((one) => one.name === candidate);
  const free = (candidate: string) => {
    const found = holder(candidate);
    return found === undefined || found.bot === bot.username;
  };
  if (free(name)) return name;
  const qualified = `${name}-${bot.username}`;
  if (free(qualified)) return qualified;
  for (let n = 2; ; n++) {
    if (free(`${qualified}-${n}`)) return `${qualified}-${n}`;
  }
}

/** Who a recipient is, the way a person would say it: `@nick · Name`, a group by its title, and the label it was given
 *  when Telegram has not said. */
export function recipientLabel(destination: Destination): string {
  const who = [destination.username ? `@${destination.username}` : null, destination.title].filter(Boolean).join(" · ");
  const kind = destination.kind === "private" || destination.kind === null ? "" : " (grupa)";
  return who === "" ? destination.name : `${who}${kind}`;
}

export const ACCOUNT_LABEL: Record<Account["status"], string> = {
  logged_out: "nie zalogowane",
  logged_in: "zalogowane",
  needs_login: "wymaga ponownego zalogowania",
};

export const DESTINATION_LABEL: Record<Destination["state"], string> = {
  pending: "czeka na tapnięcie",
  ready: "odbiera",
  blocked: "zablokował bota",
};

/** Settings the server lacks, named — a login that cannot start is not a failure of the screen. */
export function missingSettings(account: Account): string[] {
  const missing: string[] = [];
  if (!account.apiCredentialsConfigured) missing.push("TELEGRAM_API_ID i TELEGRAM_API_HASH");
  if (!account.sessionKeyConfigured) missing.push("TELEGRAM_SESSION_KEY");
  return missing;
}

/** One line under the title: what the operator needs to know before reading anything else. */
export function headline(state: GateState): string {
  return [`${state.bots} ${plural(state.bots, "bot", "boty", "botów")}`, `${state.destinationsReady} odbiera`].join(" · ");
}

function plural(n: number, one: string, few: string, many: string): string {
  if (n === 1) return one;
  const lastTwo = n % 100;
  const last = n % 10;
  return last >= 2 && last <= 4 && !(lastTwo >= 12 && lastTwo <= 14) ? few : many;
}

/** Telegram's rule, applied before a request is spent on it. */
export function botUsernameProblem(username: string): string | null {
  const cleaned = username.trim().replace(/^@/, "");
  if (cleaned === "") return null;
  if (!/^[A-Za-z0-9_]{5,32}$/.test(cleaned)) return "5–32 znaki: litery, cyfry i _";
  if (!cleaned.toLowerCase().endsWith("bot")) return "nazwa bota musi kończyć się na „bot”";
  return null;
}

