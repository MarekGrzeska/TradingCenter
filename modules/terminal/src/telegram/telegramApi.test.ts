import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { MarketDataError } from "../data/types";
import { http, HttpResponse, setupServer } from "../test/httpDouble";
import { createTelegramApi } from "./telegramApi";

/** The wire↔domain seam, and the two things that fail quietly past it: a key with a `*` in a path, and the door's reason. */

const BASE = "http://telegram.test";
const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const signal = () => new AbortController().signal;

const ACCOUNT = {
  status: "logged_in",
  username: "owner",
  phone: "+•••••••6789",
  reason: null,
  session_key_configured: true,
  api_credentials_configured: true,
};

describe("the login", () => {
  it("walks Telegram's steps and ends with the account, masked as the door sent it", async () => {
    server.use(
      http.post(`${BASE}/account/login`, () => HttpResponse.json({ step: "code", account: null, delivery: "app" })),
      http.post(`${BASE}/account/login/code`, () => HttpResponse.json({ step: "password", account: null })),
      http.post(`${BASE}/account/login/password`, () => HttpResponse.json({ step: "done", account: ACCOUNT })),
    );
    const api = createTelegramApi(BASE);

    expect(await api.loginStart("+48123456789", signal())).toEqual({ step: "code", delivery: "app", canResend: true });
    expect(await api.loginCode("12345", signal())).toEqual({ step: "password" });
    const done = await api.loginPassword("pw", signal());

    expect(done.step === "done" && done.account.phone).toBe("+•••••••6789");
  });

  it("keeps the door's own words when Telegram refuses a step", async () => {
    server.use(
      http.post(`${BASE}/account/login/code`, () =>
        HttpResponse.json({ detail: { detail: "Telegram refused the login: the code is wrong" } }, { status: 409 }),
      ),
    );

    await expect(createTelegramApi(BASE).loginCode("00000", signal())).rejects.toMatchObject({
      kind: "refused",
      message: "Telegram refused the login: the code is wrong",
    });
  });
});

describe("assignments", () => {
  it("addresses the default key as it is and a prefix as a path segment", async () => {
    const seen: string[] = [];
    const answer = (key: string) =>
      http.put(`${BASE}/assignments/${key}`, () => {
        seen.push(key);
        return HttpResponse.json({ key, destination: "operator", bot: "tc_bot", receives: true });
      });
    server.use(answer("*"), answer("youtube.film"));
    const api = createTelegramApi(BASE);

    await api.assign("*", "operator", signal());
    await api.assign("youtube.film", "operator", signal());

    expect(seen).toEqual(["*", "youtube.film"]);
  });

  it("reads a refusal to remove as a refusal, naming what still hangs on it", async () => {
    server.use(
      http.delete(`${BASE}/bots/tc_bot`, () =>
        HttpResponse.json(
          { detail: { detail: "@tc_bot still receives '*'. Move those assignments first." } },
          { status: 409 },
        ),
      ),
    );

    const failure = await createTelegramApi(BASE)
      .removeBot("tc_bot", signal())
      .catch((cause: unknown) => cause);

    expect(failure).toBeInstanceOf(MarketDataError);
    expect((failure as MarketDataError).kind).toBe("refused");
    expect((failure as MarketDataError).message).toContain("'*'");
  });
});
