import type { Account, Bot, Destination, GateState } from "./telegramApi";

/** What the screen says, decided here so the decisions can be tested without a DOM. */

/** The destinations of one bot, in the order they were made (the door lists them that way). */
export function destinationsOf(bot: Bot, destinations: Destination[]): Destination[] {
  return destinations.filter((one) => one.bot === bot.username);
}

/** The bots a recipient is already reached through, other than this one: what a person adding the same name through one
 *  more bot should be told, because each is a separate conversation that needs its own tap. */
export function otherBotsOf(name: string, bot: Bot, destinations: Destination[]): string[] {
  return destinations.filter((one) => one.name === name.trim() && one.bot !== bot.username).map((one) => one.bot);
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

