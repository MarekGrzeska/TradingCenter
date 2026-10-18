import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MarketDataError } from "../data/types";
import { AlertsView } from "./AlertsView";
import { RuleRefused, type AlertsApi, type Catalog, type PackageState, type Rule } from "./alertsApi";

/**
 * The tab from the operator's seat: that a rule says what it watches and whether it works, that a form is built from what
 * exists and sends what it was filled with, that a refusal puts its reason beside the field and keeps the form, that a
 * sentence opens a form to check rather than saving anything, and that deleting asks first.
 */

const CATALOG: Catalog = {
  tools: [
    {
      name: "get_last_price",
      description: "What a pair costs now.",
      source: "market-data",
      arguments: { properties: { symbol: { type: "string" } }, required: ["symbol"] },
      numberFields: ["close"],
    },
  ],
  eventTypes: [
    {
      name: "youtube.film.read",
      description: "A film the model read",
      attributes: { channel: { type: "string" }, impact_score: { type: "integer" } },
      seen: { channel: ["Gold Talk", "Macro"] },
    },
  ],
  recipients: [{ name: "phone", bot: "alerts_bot", receives: true }],
  gateway: true,
  minIntervalSeconds: 30,
  symbols: ["EURUSD", "XAUUSD"],
  drafting: true,
};

function state(overrides: Partial<PackageState> = {}): PackageState {
  return {
    rulesEnabled: 1,
    rulesDisabled: 0,
    rulesWithDefects: 0,
    waitingFires: 0,
    delivering: true,
    drafting: true,
    readingValues: true,
    clock: { ran: true, ageSeconds: 2, expectedSeconds: 5 },
    ...overrides,
  };
}

function rule(overrides: Partial<Rule> = {}): Rule {
  return {
    id: 1,
    name: "EURUSD powyżej 1,10",
    source: {
      kind: "condition",
      toolName: "get_last_price",
      arguments: { symbol: "EURUSD" },
      fieldPath: "close",
      comparison: "gt",
      threshold: "1.10",
      pollIntervalSeconds: 60,
    },
    destination: "phone",
    template: "{rule}: {value}",
    cooldownSeconds: 900,
    mode: "repeat",
    maxPerHour: null,
    enabled: true,
    disabledReason: null,
    defects: [],
    lastResult: false,
    lastCheckedAt: new Date("2026-10-18T12:00:00Z"),
    lastFiredAt: null,
    nextCheckAt: null,
    ...overrides,
  };
}

function api(rules: Rule[], overrides: Partial<AlertsApi> = {}, catalog: Catalog = CATALOG): AlertsApi {
  return {
    state: vi.fn(async () => state()),
    catalog: vi.fn(async () => catalog),
    rules: vi.fn(async () => rules),
    history: vi.fn(async () => ({ fires: [], checks: [] })),
    createRule: vi.fn(async (input) => rule({ ...input, id: 9 })),
    replaceRule: vi.fn(),
    setEnabled: vi.fn(async (id, enabled) => rule({ id, enabled })),
    deleteRule: vi.fn(async () => undefined),
    draft: vi.fn(),
    ...overrides,
  };
}

describe("AlertsView", () => {
  it("shows what each rule watches and whether it works, and says what the package cannot do", async () => {
    const client = api([rule(), rule({ id: 2, name: "Zepsuta", defects: [{ field: "destination", message: "adresat zniknął" }] })], {
      state: vi.fn(async () => state({ delivering: false })),
    });

    render(<AlertsView api={client} />);

    expect(await screen.findAllByText("get_last_price(symbol=EURUSD).close powyżej 1.10 · co 60 s")).toHaveLength(2);
    expect(screen.getByText("działa")).toBeInTheDocument();
    expect(screen.getByText(/ma wadę/)).toBeInTheDocument();
    expect(screen.getByText("adresat zniknął")).toBeInTheDocument();
    expect(screen.getByText(/nie ma bramy Telegrama|bramy Telegrama w tym procesie/)).toBeInTheDocument();
  });

  it("says a workbench without the package has none, and is not a list with no rules", async () => {
    const client = api([], {
      state: vi.fn(async () => {
        throw new MarketDataError("not-found", "Not Found");
      }),
    });

    render(<AlertsView api={client} />);

    expect(await screen.findByText(/nie ma pakietu alertów/)).toBeInTheDocument();
    expect(client.rules).not.toHaveBeenCalled();
  });

  it("builds a rule from what exists and sends what it was filled with", async () => {
    const client = api([]);
    render(<AlertsView api={client} />);

    await userEvent.click(await screen.findByRole("button", { name: "Nowa reguła…" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Nazwa"), "Złoto w górę");
    await userEvent.selectOptions(within(dialog).getByRole("combobox", { name: /^symbol/ }), "XAUUSD");
    await userEvent.type(within(dialog).getByLabelText("Próg"), "3000");
    await userEvent.click(within(dialog).getByRole("button", { name: "Zapisz" }));

    expect(client.createRule).toHaveBeenCalledTimes(1);
    expect(vi.mocked(client.createRule).mock.calls[0][0]).toMatchObject({
      name: "Złoto w górę",
      destination: "phone",
      source: { kind: "condition", toolName: "get_last_price", arguments: { symbol: "XAUUSD" }, fieldPath: "close", threshold: "3000" },
    });
  });

  it("puts the reason beside the field it is about and keeps the form open when a rule is refused", async () => {
    const createRule = vi
      .fn()
      .mockRejectedValueOnce(
        new RuleRefused("the rule cannot work as written", [
          { field: "source.poll_interval_seconds", message: "a rule may look no more often than every 30 s" },
        ]),
      );
    render(<AlertsView api={api([], { createRule })} />);

    await userEvent.click(await screen.findByRole("button", { name: "Nowa reguła…" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Nazwa"), "Za szybka");
    await userEvent.type(within(dialog).getByLabelText("Próg"), "1");
    await userEvent.click(within(dialog).getByRole("button", { name: "Zapisz" }));

    const reason = await within(dialog).findByText("a rule may look no more often than every 30 s");
    expect(reason.closest("label")).toHaveTextContent("Sprawdzaj co");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("opens a form to check from a sentence and saves nothing by itself", async () => {
    const draft = vi.fn(async () => ({
      understood: "Powiadom, gdy EURUSD przekroczy 1,10.",
      rule: {
        name: "EURUSD przebił 1,10",
        source: rule().source,
        destination: "",
        template: "",
        cooldownSeconds: 3600,
        mode: "repeat" as const,
        maxPerHour: null,
        enabled: true,
      },
      defects: [{ field: "destination", message: "zdanie nie mówi, kogo powiadomić" }],
      notes: [],
    }));
    const client = api([], { draft });
    render(<AlertsView api={client} />);

    await userEvent.type(await screen.findByLabelText(/Albo opisz zdaniem/), "daj znać, gdy EURUSD przebije 1,10");
    await userEvent.click(screen.getByRole("button", { name: "Zaproponuj regułę" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText("Nazwa")).toHaveValue("EURUSD przebił 1,10");
    expect(within(dialog).getByText("zdanie nie mówi, kogo powiadomić")).toBeInTheDocument();
    expect(within(dialog).getByText(/Zrozumiałem to tak/)).toBeInTheDocument();
    expect(client.createRule).not.toHaveBeenCalled();
  });

  it("keeps saving out of reach of a draft with a flaw until the operator has changed something", async () => {
    const draft = vi.fn(async () => ({
      understood: "Powiadom, gdy DOGE przekroczy 1.",
      rule: { ...rule(), id: undefined, name: "DOGE powyżej 1" },
      defects: [{ field: "source.arguments.symbol", message: "archiwum nie śledzi DOGE" }],
      notes: [],
    }));
    render(<AlertsView api={api([], { draft })} />);

    await userEvent.type(await screen.findByLabelText(/Albo opisz zdaniem/), "daj znać, gdy DOGE przebije 1");
    await userEvent.click(screen.getByRole("button", { name: "Zaproponuj regułę" }));
    const dialog = await screen.findByRole("dialog");

    expect(within(dialog).getByRole("button", { name: "Zapisz" })).toBeDisabled();

    await userEvent.type(within(dialog).getByLabelText("Nazwa"), "!");

    expect(within(dialog).getByRole("button", { name: "Zapisz" })).toBeEnabled();
  });

  it("lets a draft be saved when all the model had to say was a remark about the sentence", async () => {
    const draft = vi.fn(async () => ({
      understood: "Powiadom o postach.",
      rule: { ...rule(), id: undefined, name: "Nowy post" },
      defects: [{ field: "sentence", message: "nie da się ograniczyć reguły do Truth Social" }],
      notes: [],
    }));
    render(<AlertsView api={api([], { draft })} />);

    await userEvent.type(await screen.findByLabelText(/Albo opisz zdaniem/), "daj znać o postach z Truth Social");
    await userEvent.click(screen.getByRole("button", { name: "Zaproponuj regułę" }));
    const dialog = await screen.findByRole("dialog");

    expect(within(dialog).getByText(/nie da się ograniczyć/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Zapisz" })).toBeEnabled();
  });

  it("shows a fire the cap held back as held back, with the reason", async () => {
    const client = api([rule()], {
      history: vi.fn(async () => ({
        fires: [{ at: new Date("2026-10-18T12:00:00Z"), state: "throttled" as const, reason: "the rule has already told 20 times in the last hour", text: "EURUSD powyżej 1,10: 1.1021" }],
        checks: [],
      })),
    });
    render(<AlertsView api={client} />);

    await userEvent.click(await screen.findByRole("button", { name: "Historia" }));

    expect(await screen.findByText(/zdławiona \(the rule has already told 20 times/)).toBeInTheDocument();
  });

  it("offers a channel outside the ones seen only by choosing \"inna wartość\"", async () => {
    const film = rule({
      id: 2,
      name: "filmy",
      source: { kind: "event", eventType: "youtube.film.read", filter: [{ attribute: "channel", op: "eq", value: "Gold Talk" }] },
    });
    render(<AlertsView api={api([film])} />);

    await userEvent.click(await screen.findByRole("button", { name: "Edytuj…" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByLabelText("inna wartość")).not.toBeInTheDocument();

    await userEvent.selectOptions(within(dialog).getByDisplayValue("Gold Talk"), "inna wartość…");

    expect(within(dialog).getByLabelText("inna wartość")).toBeInTheDocument();
  });

  it("switches the sentence box off, with the setting that would turn it on, when there is no key", async () => {
    render(<AlertsView api={api([], {}, { ...CATALOG, drafting: false })} />);

    expect(await screen.findByText(/ALERTS_OPENAI_API_KEY/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Zaproponuj regułę" })).toBeDisabled();
  });

  it("shows what became of a rule, including the times it could not look", async () => {
    const client = api([rule()], {
      history: vi.fn(async () => ({
        fires: [{ at: new Date("2026-10-18T12:00:00Z"), state: "delivered" as const, reason: null, text: "EURUSD powyżej 1,10: 1.1021" }],
        checks: [{ at: new Date("2026-10-18T11:00:00Z"), outcome: "unavailable" as const, reason: "market-data could not answer" }],
      })),
    });
    render(<AlertsView api={client} />);

    await userEvent.click(await screen.findByRole("button", { name: "Historia" }));

    expect(await screen.findByText(/dotarła: EURUSD powyżej 1,10: 1.1021/)).toBeInTheDocument();
    expect(screen.getByText(/nie mogła odczytać wartości: market-data could not answer/)).toBeInTheDocument();
  });

  it("deletes only after asking, and says that switching off is the reversible one", async () => {
    const client = api([rule()]);
    render(<AlertsView api={client} />);

    await userEvent.click(await screen.findByRole("button", { name: "Usuń…" }));
    expect(screen.getByText(/Wyłączenie jest odwracalne/)).toBeInTheDocument();
    expect(client.deleteRule).not.toHaveBeenCalled();

    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Usuń" }));

    expect(client.deleteRule).toHaveBeenCalledWith(1, expect.anything());
  });
});
