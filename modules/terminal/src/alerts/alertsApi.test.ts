import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { MarketDataError } from "../data/types";
import { http, HttpResponse, setupServer } from "../test/httpDouble";
import { createAlertsApi, RuleRefused, type RuleInput } from "./alertsApi";

/**
 * The wire↔domain seam. What fails quietly here is a refusal that names fields being flattened to a sentence, a rule going out
 * with its source in the wrong shape, and a package that is not there being read as a package with nothing in it.
 */

const BASE = "http://alerts.test";

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const signal = () => new AbortController().signal;

const RULE_OUT = {
  id: 7,
  name: "EURUSD powyżej 1,10",
  source: {
    kind: "condition",
    tool_name: "get_last_price",
    arguments: { symbol: "EURUSD" },
    field_path: "close",
    comparison: "gt",
    threshold: "1.10",
    poll_interval_seconds: 60,
  },
  destination: "phone",
  bot: null,
  template: "{rule}: {value}",
  cooldown_seconds: 900,
  mode: "repeat",
  max_per_hour: null,
  enabled: true,
  disabled_reason: null,
  defects: [{ field: "destination", message: "gone" }],
  created_by: "operator",
  created_at: "2026-10-18T10:00:00Z",
  updated_at: "2026-10-18T10:00:00Z",
  last_result: null,
  last_checked_at: "2026-10-18T12:00:00Z",
  last_fired_at: null,
  next_check_at: null,
};

const INPUT: RuleInput = {
  name: "Filmy",
  source: { kind: "event", eventType: "youtube.film.read", filter: [{ attribute: "impact_score", op: "gte", value: 7 }] },
  destination: "phone",
  bot: null,
  template: "",
  cooldownSeconds: null,
  mode: "repeat",
  maxPerHour: null,
  enabled: true,
};

describe("rules", () => {
  it("maps a rule with its moments, its source and the reasons it is wrong", async () => {
    server.use(http.get(`${BASE}/rules`, () => HttpResponse.json([RULE_OUT])));

    const [rule] = await createAlertsApi(BASE).rules(signal());

    expect(rule.source).toEqual({
      kind: "condition",
      toolName: "get_last_price",
      arguments: { symbol: "EURUSD" },
      fieldPath: "close",
      comparison: "gt",
      threshold: "1.10",
      pollIntervalSeconds: 60,
    });
    expect(rule.lastCheckedAt).toEqual(new Date("2026-10-18T12:00:00Z"));
    expect(rule.lastResult).toBeNull();
    expect(rule.defects).toEqual([{ field: "destination", message: "gone" }]);
  });

  it("sends a rule in the contract's shape, with nothing the operator left empty invented", async () => {
    let sent: unknown;
    server.use(
      http.post(`${BASE}/rules`, async ({ request }) => {
        sent = await request.json();
        return HttpResponse.json({ ...RULE_OUT, source: { kind: "event", event_type: "youtube.film.read", filter: [] } }, { status: 201 });
      }),
    );

    await createAlertsApi(BASE).createRule(INPUT, signal());

    expect(sent).toEqual({
      name: "Filmy",
      source: { kind: "event", event_type: "youtube.film.read", filter: [{ attribute: "impact_score", op: "gte", value: 7 }] },
      destination: "phone",
      bot: null,
      template: "",
      cooldown_seconds: null,
      mode: "repeat",
      max_per_hour: null,
      enabled: true,
    });
  });

  it("keeps every field a refusal names, not only its first sentence", async () => {
    server.use(
      http.post(`${BASE}/rules`, () =>
        HttpResponse.json(
          {
            detail: {
              detail: "the rule cannot work as written: nobody has announced an event type 'x' (and 1 more)",
              defects: [
                { field: "source.event_type", message: "nobody has announced an event type 'x'" },
                { field: "destination", message: "'nobody' is not a recipient" },
              ],
            },
          },
          { status: 422 },
        ),
      ),
    );

    const refused = await createAlertsApi(BASE).createRule(INPUT, signal()).catch((cause: unknown) => cause);

    expect(refused).toBeInstanceOf(RuleRefused);
    expect((refused as RuleRefused).defects.map((one) => one.field)).toEqual(["source.event_type", "destination"]);
    expect((refused as RuleRefused).message).toContain("cannot work as written");
  });

  it("lets a refusal with no fields through as the module's sentence", async () => {
    server.use(http.put(`${BASE}/rules/9`, () => HttpResponse.json({ detail: { detail: "there is no rule 9", defects: [] } }, { status: 404 })));

    const failed = await createAlertsApi(BASE).replaceRule(9, INPUT, signal()).catch((cause: unknown) => cause);

    expect(failed).toBeInstanceOf(MarketDataError);
    expect((failed as MarketDataError).kind).toBe("not-found");
  });
});

describe("a package that is not there", () => {
  it("is a not-found the view can tell from an empty list", async () => {
    server.use(http.get(`${BASE}/state`, () => new HttpResponse(null, { status: 404, statusText: "Not Found" })));

    const failed = await createAlertsApi(BASE).state(signal()).catch((cause: unknown) => cause);

    expect(failed).toMatchObject({ kind: "not-found" });
  });
});

describe("drafts", () => {
  it("maps a proposal into the same shape the form is filled with, and keeps its reasons", async () => {
    server.use(
      http.post(`${BASE}/drafts`, () =>
        HttpResponse.json({
          understood: "Powiadom, gdy EURUSD przekroczy 1,10.",
          rule: {
            name: "EURUSD",
            source: RULE_OUT.source,
            destination: "",
            bot: null,
            template: "",
            cooldown_seconds: 3600,
            mode: "repeat",
            max_per_hour: null,
            enabled: true,
          },
          defects: [{ field: "destination", message: "choose a recipient" }],
          notes: ["wybrano domyślnie"],
        }),
      ),
    );

    const draft = await createAlertsApi(BASE).draft("EURUSD powyżej 1,10", signal());

    expect(draft.rule?.cooldownSeconds).toBe(3600);
    expect(draft.rule?.source).toMatchObject({ kind: "condition", toolName: "get_last_price" });
    expect(draft.defects).toEqual([{ field: "destination", message: "choose a recipient" }]);
    expect(draft.notes).toEqual(["wybrano domyślnie"]);
  });

  it("reads a sentence that made no rule as a draft with none", async () => {
    server.use(
      http.post(`${BASE}/drafts`, () =>
        HttpResponse.json({ understood: "", rule: null, defects: [{ field: "sentence", message: "Ethereum is not followed" }], notes: [] }),
      ),
    );

    expect((await createAlertsApi(BASE).draft("alert na Ethereum", signal())).rule).toBeNull();
  });
});

describe("the catalogue", () => {
  it("brings the attributes out of the schema and the values an attribute has had", async () => {
    server.use(
      http.get(`${BASE}/catalog`, () =>
        HttpResponse.json({
          tools: [
            { name: "get_last_price", description: "d", source: "market-data", arguments: { properties: {} }, number_fields: ["close"] },
          ],
          event_types: [
            {
              name: "youtube.film.read",
              description: "a film",
              schema: { type: "object", properties: { channel: { type: "string", "x-seen-values": true } } },
              announced_by: "the YouTube archive",
              last_announced_at: "2026-10-18T10:00:00Z",
              seen: { channel: ["Gold Talk"] },
            },
          ],
          destinations: [{ name: "phone", bot: "alerts_bot", receives: true }],
          gateway: true,
          min_interval_seconds: 30,
          symbols: ["EURUSD"],
          drafting: false,
        }),
      ),
    );

    const catalog = await createAlertsApi(BASE).catalog(signal());

    expect(catalog.tools[0].numberFields).toEqual(["close"]);
    expect(catalog.eventTypes[0].attributes.channel.type).toBe("string");
    expect(catalog.eventTypes[0].seen).toEqual({ channel: ["Gold Talk"] });
    expect(catalog.recipients).toEqual([{ name: "phone", bot: "alerts_bot", receives: true }]);
    expect(catalog.drafting).toBe(false);
  });
});
