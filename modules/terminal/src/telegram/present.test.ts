import { describe, expect, it } from "vitest";
import { botUsernameProblem, freeNameFor, headline, missingSettings } from "./present";
import type { GateState } from "./telegramApi";

describe("what the operator types", () => {
  it.each([
    ["", null],
    ["tc_alerts_bot", null],
    ["@tc_alerts_bot", null],
    ["tc_alerts", "nazwa bota musi kończyć się na „bot”"],
    ["abot", "5–32 znaki: litery, cyfry i _"],
  ])("judges the bot username %j before a request is spent on it", (username, problem) => {
    expect(botUsernameProblem(username)).toBe(problem);
  });
});

describe("headline and missing settings", () => {
  const base: GateState = {
    account: {
      status: "logged_out",
      username: null,
      phone: null,
      reason: null,
      sessionKeyConfigured: true,
      apiCredentialsConfigured: false,
    },
    canCreateBots: false,
    bots: 2,
    destinations: 2,
    destinationsReady: 1,
  };

  it("counts in Polish", () => {
    expect(headline(base)).toBe("2 boty · 1 odbiera");
  });

  it("names the settings the server lacks", () => {
    expect(missingSettings(base.account)).toEqual(["TELEGRAM_API_ID i TELEGRAM_API_HASH"]);
  });
});

describe("freeNameFor", () => {
  const bot = { username: "second_bot", title: "Second", createdHere: false };
  const held = (name: string, owner: string) => ({
    name,
    bot: owner,
    state: "ready" as const,
    receives: true,
    username: null,
    title: null,
    kind: null,
  });

  it("keeps a name nobody holds, and a name this very bot holds (a fresh link for the same recipient)", () => {
    expect(freeNameFor("operator", bot, [])).toBe("operator");
    expect(freeNameFor("operator", bot, [held("operator", "second_bot")])).toBe("operator");
  });

  it("qualifies a name another bot holds, so one person can receive through many bots", () => {
    expect(freeNameFor("operator", bot, [held("operator", "first_bot")])).toBe("operator-second_bot");
  });

  it("numbers it when even the qualified name is taken", () => {
    const taken = [held("operator", "first_bot"), held("operator-second_bot", "third_bot")];

    expect(freeNameFor("operator", bot, taken)).toBe("operator-second_bot-2");
  });
});
