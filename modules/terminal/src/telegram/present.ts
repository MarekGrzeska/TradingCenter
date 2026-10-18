import type { Account, Assignment, Bot, Destination, GateState, Purpose } from "./telegramApi";

/** What the screen says, decided here so the decisions can be tested without a DOM. */

export type Origin = { kind: "own" | "prefix" | "default"; key: string } | { kind: "none" };

/** Where a purpose gets its recipient from: its own assignment, a prefix of it, the default — or nowhere. The operator has
 *  to see which, because a literal typo in a prefix assigns nothing and looks the same as an assignment that works. */
export function originOf(purpose: Purpose): Origin {
  if (purpose.destination === null || purpose.assignedBy === null) return { kind: "none" };
  if (purpose.assignedBy === purpose.name) return { kind: "own", key: purpose.assignedBy };
  if (purpose.assignedBy === "*") return { kind: "default", key: "*" };
  return { kind: "prefix", key: purpose.assignedBy };
}

export function originLabel(origin: Origin): string {
  switch (origin.kind) {
    case "own":
      return "przypisane wprost";
    case "prefix":
      return `z przypisania „${origin.key}”`;
    case "default":
      return "z przypisania domyślnego (*)";
    case "none":
      return "nikt nie słucha";
  }
}

/** Purposes nobody hears come first — they are what the operator opened the tab to fix — then by name. */
export function orderedPurposes(purposes: Purpose[]): Purpose[] {
  return [...purposes].sort((a, b) => {
    const heardA = a.destination === null ? 0 : 1;
    const heardB = b.destination === null ? 0 : 1;
    return heardA - heardB || a.name.localeCompare(b.name);
  });
}

export function unheard(purposes: Purpose[]): Purpose[] {
  return purposes.filter((one) => one.destination === null);
}

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

/** The assignments that end at one of this bot's recipients. */
export function assignmentsOf(bot: Bot, assignments: Assignment[]): Assignment[] {
  return assignments.filter((one) => one.bot === bot.username);
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
  const parts = [`${state.bots} ${plural(state.bots, "bot", "boty", "botów")}`, `${state.destinationsReady} odbiera`];
  if (state.purposesUnheard > 0) {
    parts.push(
      `${state.purposesUnheard} ${plural(state.purposesUnheard, "cel", "cele", "celów")} bez odbiorcy`,
    );
  }
  return parts.join(" · ");
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

/** A purpose or assignment key as the door will accept it — told here, so the dialog says what is wrong with it. */
export function keyProblem(key: string): string | null {
  if (key === "" || key === "*") return null;
  if (key.length > 120 || !/^[a-z0-9][a-z0-9_-]*(\.[a-z0-9][a-z0-9_-]*)*$/.test(key)) {
    return "małe litery, cyfry, _ i - w niepustych segmentach oddzielonych kropką, albo samo *";
  }
  return null;
}
