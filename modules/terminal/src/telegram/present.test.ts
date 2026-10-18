import { describe, expect, it } from "vitest";
import { botUsernameProblem, headline, missingSettings, otherBotsOf } from "./present";
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

describe("otherBotsOf", () => {
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

  it("names the other bots a recipient already receives through, so a second one is added knowingly", () => {
    expect(otherBotsOf("operator", bot, [held("operator", "first_bot"), held("operator", "third_bot")])).toEqual(["first_bot", "third_bot"]);
  });

  it("says nothing for a new name, for this bot's own binding, and for somebody else's name", () => {
    expect(otherBotsOf("operator", bot, [])).toEqual([]);
    expect(otherBotsOf("operator", bot, [held("operator", "second_bot")])).toEqual([]);
    expect(otherBotsOf("operator", bot, [held("risk", "first_bot")])).toEqual([]);
  });
});
