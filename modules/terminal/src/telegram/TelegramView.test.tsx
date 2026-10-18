import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MarketDataError } from "../data/types";
import { TelegramView } from "./TelegramView";
import type { Bot, Destination, GateState, TelegramApi } from "./telegramApi";

/**
 * The tab from the operator's seat: that it points to the Alerts tab for who is told what, that the account logs in through
 * Telegram's steps, that a refusal stays in the dialog in the door's words, and that
 * the tap on a start link turns an address on without a reload.
 */

const LOGGED_IN: GateState = {
  account: {
    status: "logged_in",
    username: "owner",
    phone: "+•••••••6789",
    reason: null,
    sessionKeyConfigured: true,
    apiCredentialsConfigured: true,
  },
  canCreateBots: true,
  bots: 1,
  destinations: 1,
  destinationsReady: 1,
};

const LOGGED_OUT: GateState = {
  ...LOGGED_IN,
  account: { ...LOGGED_IN.account, status: "logged_out", username: null, phone: null },
  canCreateBots: false,
};

const BOT: Bot = { username: "tc_alerts_bot", title: "Alerts", createdHere: true };
const OPERATOR: Destination = {
  name: "operator",
  bot: "tc_alerts_bot",
  state: "ready",
  receives: true,
  username: "marek",
  title: "Marek G.",
  kind: "private",
};

function api(overrides: Partial<TelegramApi> = {}): TelegramApi {
  return {
    state: vi.fn(async () => LOGGED_IN),
    loginStart: vi.fn(),
    loginCode: vi.fn(),
    loginResend: vi.fn(),
    loginQrStart: vi.fn(async () => ({ status: "waiting" as const, url: "tg://login?token=abc", account: null, reason: null })),
    loginQrState: vi.fn(async () => ({ status: "waiting" as const, url: "tg://login?token=abc", account: null, reason: null })),
    loginPassword: vi.fn(),
    logout: vi.fn(async () => true),
    bots: vi.fn(async () => [BOT]),
    adoptBot: vi.fn(),
    createBot: vi.fn(),
    rotateBot: vi.fn(),
    removeBot: vi.fn(async () => undefined),
    destinations: vi.fn(async () => [OPERATOR]),
    offerDestination: vi.fn(),
    removeDestination: vi.fn(async () => undefined),
    sendMessage: vi.fn(async () => 77),
    ...overrides,
  };
}

afterEach(() => {
  vi.useRealTimers();
});

describe("TelegramView", () => {
  it("points to the Alerts tab for who is told what, since this tab is only the road", async () => {
    render(<TelegramView api={api()} />);

    expect(await screen.findByText(/ustawiasz w zakładce\s+Alerty/)).toBeInTheDocument();
  });

  it("shows only the bots until one is opened, and then who receives through it and a message to try it with", async () => {
    render(<TelegramView api={api()} />);

    await userEvent.click(await screen.findByRole("button", { name: /pokaż odbiorców/ }));

    expect(screen.getAllByText("@marek · Marek G.").length).toBeGreaterThan(0);
    expect(screen.getByRole("combobox", { name: "odbiorca wiadomości" })).toBeInTheDocument();
  });

  it("keeps a closed bot's actions in reach and its recipients out of the way", async () => {
    render(<TelegramView api={api()} />);

    expect(await screen.findByRole("button", { name: "Usuń bota @tc_alerts_bot" })).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "odbiorca wiadomości" })).not.toBeInTheDocument();
  });

  it("warns, before a bot or a recipient is removed, that the rules pointing at it stop delivering", async () => {
    render(<TelegramView api={api()} />);

    await userEvent.click(await screen.findByRole("button", { name: "Usuń bota @tc_alerts_bot" }));

    expect(screen.getByText(/przestaną dostarczać/)).toBeInTheDocument();
  });

  it("keeps the door's reason in the dialog when it refuses to remove a bot", async () => {
    const removeBot = vi
      .fn()
      .mockRejectedValue(new MarketDataError("refused", "Telegram would not delete @tc_alerts_bot: the creator bot did not answer."));
    render(<TelegramView api={api({ removeBot })} />);

    await userEvent.click(await screen.findByRole("button", { name: "Usuń bota @tc_alerts_bot" }));
    await userEvent.click(screen.getByRole("button", { name: "Usuń bota" }));

    expect(await screen.findByText(/the creator bot did not answer/)).toBeInTheDocument();
    expect(removeBot).toHaveBeenCalledTimes(1);
    expect(screen.getAllByText("@tc_alerts_bot").length).toBeGreaterThan(0);
  });

  it("logs the account in through Telegram's steps, and shows the password field only when asked", async () => {
    const loginStart = vi.fn(async () => ({ step: "code" as const, delivery: "app" as const, canResend: true }));
    const loginCode = vi.fn(async () => ({ step: "password" as const }));
    const loginPassword = vi.fn(async () => ({ step: "done" as const, account: LOGGED_IN.account }));
    render(
      <TelegramView api={api({ state: vi.fn(async () => LOGGED_OUT), loginStart, loginCode, loginPassword })} />,
    );

    await userEvent.click(await screen.findByRole("button", { name: "Zaloguj konto…" }));
    await userEvent.click(await screen.findByRole("button", { name: "Zaloguj numerem telefonu zamiast tego" }));
    expect(screen.getByText(/osobnego konta tylko do botów/)).toBeInTheDocument();
    await userEvent.type(screen.getByPlaceholderText("+48123456789"), "+48123456789");
    await userEvent.click(screen.getByRole("button", { name: "Wyślij kod" }));
    await userEvent.type(await screen.findByLabelText(/Kod, który przyszedł/), "12345");
    await userEvent.click(screen.getByRole("button", { name: "Zaloguj" }));
    await userEvent.type(await screen.findByLabelText("Hasło dwuetapowe tego konta"), "hunter2");
    await userEvent.click(screen.getByRole("button", { name: "Zaloguj" }));

    expect(loginStart).toHaveBeenCalledWith("+48123456789", expect.anything());
    expect(loginCode).toHaveBeenCalledWith("12345", expect.anything());
    expect(loginPassword).toHaveBeenCalledWith("hunter2", expect.anything());
  });

  it("says where the code went and asks for another way when it did not come", async () => {
    const loginStart = vi.fn(async () => ({ step: "code" as const, delivery: "app" as const, canResend: true }));
    const loginResend = vi.fn(async () => ({ step: "code" as const, delivery: "sms" as const, canResend: false }));
    render(<TelegramView api={api({ state: vi.fn(async () => LOGGED_OUT), loginStart, loginResend })} />);

    await userEvent.click(await screen.findByRole("button", { name: "Zaloguj konto…" }));
    await userEvent.click(await screen.findByRole("button", { name: "Zaloguj numerem telefonu zamiast tego" }));
    await userEvent.type(screen.getByPlaceholderText("+48123456789"), "+48123456789");
    await userEvent.click(screen.getByRole("button", { name: "Wyślij kod" }));

    expect(await screen.findByText(/aplikacji Telegram zalogowanej na tym koncie/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Nie dostałem kodu/ }));

    expect(await screen.findByText(/Kod poszedł SMS-em/)).toBeInTheDocument();
    expect(loginResend).toHaveBeenCalledTimes(1);
  });

  it("sends a message through a bot to one of its recipients, and says what Telegram answered", async () => {
    const sendMessage = vi.fn(async () => 4242);
    render(<TelegramView api={api({ sendMessage })} />);

    await userEvent.click(await screen.findByRole("button", { name: /pokaż odbiorców/ }));
    await userEvent.type(screen.getByRole("textbox", { name: "treść wiadomości" }), "test z terminala");
    await userEvent.click(screen.getByRole("button", { name: "Wyślij" }));

    expect(await screen.findByText(/Wysłane \(wiadomość nr 4242/)).toBeInTheDocument();
    expect(sendMessage).toHaveBeenCalledWith("operator", "test z terminala", expect.anything());
  });

  it("keeps Telegram's refusal beside the message when it cannot be sent", async () => {
    const sendMessage = vi.fn().mockRejectedValue(new MarketDataError("refused", "'operator' blocked the bot"));
    render(<TelegramView api={api({ sendMessage })} />);

    await userEvent.click(await screen.findByRole("button", { name: /pokaż odbiorców/ }));
    await userEvent.type(screen.getByRole("textbox", { name: "treść wiadomości" }), "halo");
    await userEvent.click(screen.getByRole("button", { name: "Wyślij" }));

    expect(await screen.findByText(/blocked the bot/)).toBeInTheDocument();
  });

  it("offers the same person a second bot under a name of its own instead of refusing the name", async () => {
    const other: Bot = { username: "tc_second_bot", title: "Second", createdHere: false };
    const offerDestination = vi.fn(async () => ({
      destination: { ...OPERATOR, name: "operator-tc_second_bot", bot: other.username, receives: false, state: "pending" as const },
      url: "https://t.me/tc_second_bot?start=abc",
      expiresAt: new Date(Date.now() + 30 * 60_000),
    }));
    render(<TelegramView api={api({ bots: vi.fn(async () => [BOT, other]), offerDestination })} />);

    const adds = await screen.findAllByRole("button", { name: "Dodaj odbiorcę…" });
    await userEvent.click(adds[1]);

    expect(screen.getByText(/dostanie nazwę „operator-tc_second_bot”/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Pokaż link" }));
    expect(offerDestination).toHaveBeenCalledWith("operator-tc_second_bot", "tc_second_bot", expect.anything());
  });

  it("does not offer another way when Telegram has none, and says where the code is instead", async () => {
    const loginStart = vi.fn(async () => ({ step: "code" as const, delivery: "app" as const, canResend: false }));
    render(<TelegramView api={api({ state: vi.fn(async () => LOGGED_OUT), loginStart })} />);

    await userEvent.click(await screen.findByRole("button", { name: "Zaloguj konto…" }));
    await userEvent.click(await screen.findByRole("button", { name: "Zaloguj numerem telefonu zamiast tego" }));
    await userEvent.type(screen.getByPlaceholderText("+48123456789"), "+48123456789");
    await userEvent.click(screen.getByRole("button", { name: "Wyślij kod" }));

    expect(await screen.findByText(/nie oferuje dla tego numeru innej drogi/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Nie dostałem kodu/ })).not.toBeInTheDocument();
  });

  it("remembers the number in this browser once a code was sent, so the next login is one click", async () => {
    localStorage.removeItem("tc.telegram.ownerPhone");
    const loginStart = vi.fn(async () => ({ step: "code" as const, delivery: "app" as const, canResend: true }));
    const first = render(<TelegramView api={api({ state: vi.fn(async () => LOGGED_OUT), loginStart })} />);
    await userEvent.click(await screen.findByRole("button", { name: "Zaloguj konto…" }));
    await userEvent.click(await screen.findByRole("button", { name: "Zaloguj numerem telefonu zamiast tego" }));
    await userEvent.type(screen.getByPlaceholderText("+48123456789"), "+48111222333");
    await userEvent.click(screen.getByRole("button", { name: "Wyślij kod" }));
    await screen.findByLabelText(/Kod, który przyszedł/);
    first.unmount();

    render(<TelegramView api={api({ state: vi.fn(async () => LOGGED_OUT), loginStart })} />);
    await userEvent.click(await screen.findByRole("button", { name: "Zaloguj konto…" }));
    await userEvent.click(await screen.findByRole("button", { name: "Zaloguj numerem telefonu zamiast tego" }));

    expect(screen.getByPlaceholderText("+48123456789")).toHaveValue("+48111222333");
    localStorage.removeItem("tc.telegram.ownerPhone");
  });

  it("logs in by QR code first: shows the code, and finishes when the scan arrives", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const loginQrState = vi
      .fn<TelegramApi["loginQrState"]>()
      .mockResolvedValue({ status: "waiting", url: "tg://login?token=abc", account: null, reason: null });
    const state = vi.fn<TelegramApi["state"]>().mockResolvedValue(LOGGED_OUT);
    render(<TelegramView api={api({ state, loginQrState })} />);

    await user.click(await screen.findByRole("button", { name: "Zaloguj konto…" }));

    expect(await screen.findByRole("img", { name: "Kod QR logowania konta-właściciela" })).toBeInTheDocument();
    expect(screen.getByText(/Połącz urządzenie/)).toBeInTheDocument();

    loginQrState.mockResolvedValue({ status: "done", url: null, account: LOGGED_IN.account, reason: null });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100);
    });

    expect(screen.queryByRole("img", { name: "Kod QR logowania konta-właściciela" })).not.toBeInTheDocument();
  });

  it("names the settings the server lacks instead of offering a login that cannot start", async () => {
    const lacking: GateState = {
      ...LOGGED_OUT,
      account: { ...LOGGED_OUT.account, sessionKeyConfigured: false },
    };
    render(<TelegramView api={api({ state: vi.fn(async () => lacking) })} />);

    expect(await screen.findByText(/TELEGRAM_SESSION_KEY/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Zaloguj konto…" })).toBeDisabled();
  });

  it("says where to begin on a door with nothing in it, instead of showing empty tables", async () => {
    render(
      <TelegramView
        api={api({
          state: vi.fn(async () => ({ ...LOGGED_OUT, bots: 0, destinations: 0, destinationsReady: 0 })),
          bots: vi.fn(async () => []),
          destinations: vi.fn(async () => []),
        })}
      />,
    );

    expect(await screen.findByText(/Zacznij od zalogowania konta-właściciela/)).toBeInTheDocument();
  });

  it("says the door does not answer, and does not show its lists as empty", async () => {
    const down = new MarketDataError("unreachable", "telegram is not reachable");
    render(<TelegramView api={api({ state: vi.fn().mockRejectedValue(down) })} />);

    expect(await screen.findByText(/telegram is not reachable/)).toBeInTheDocument();
    expect(screen.queryByText(/Brama nie zna jeszcze żadnego bota/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Zacznij od zalogowania/)).not.toBeInTheDocument();
  });

  it("says a start link has expired and issues a new one in one action", async () => {
    const waiting: Destination = {
      name: "phone",
      bot: BOT.username,
      state: "pending",
      receives: false,
      username: null,
      title: null,
      kind: null,
    };
    const offerDestination = vi
      .fn()
      .mockResolvedValueOnce({
        destination: waiting,
        url: "https://t.me/tc_alerts_bot?start=old",
        expiresAt: new Date(Date.now() - 1000),
      })
      .mockResolvedValueOnce({
        destination: waiting,
        url: "https://t.me/tc_alerts_bot?start=fresh",
        expiresAt: new Date(Date.now() + 30 * 60_000),
      });
    render(<TelegramView api={api({ offerDestination })} />);

    await userEvent.click(await screen.findByRole("button", { name: "Dodaj odbiorcę…" }));
    await userEvent.click(screen.getByRole("button", { name: "Pokaż link" }));

    expect(await screen.findByText(/Odnośnik wygasł/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Wydaj nowy link" }));

    expect(await screen.findByRole("link", { name: /start=fresh/ })).toBeInTheDocument();
    expect(offerDestination).toHaveBeenCalledTimes(2);
  });

  it("shows a code for the start link and turns the address on when the tap arrives", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const waiting: Destination = {
      name: "phone",
      bot: BOT.username,
      state: "pending",
      receives: false,
      username: null,
      title: null,
      kind: null,
    };
    const tapped: Destination = { ...waiting, state: "ready", receives: true };
    const destinations = vi.fn<TelegramApi["destinations"]>().mockResolvedValue([OPERATOR, waiting]);
    const offerDestination = vi.fn(async () => ({
      destination: waiting,
      url: "https://t.me/tc_alerts_bot?start=abc123",
      expiresAt: new Date(Date.now() + 30 * 60_000),
    }));
    render(<TelegramView api={api({ destinations, offerDestination })} />);

    await user.click(await screen.findByRole("button", { name: "Dodaj odbiorcę…" }));
    const name = screen.getByLabelText(/Nazwa odbiorcy/);
    await user.clear(name);
    await user.type(name, "phone");
    await user.click(screen.getByRole("button", { name: "Pokaż link" }));

    expect(await screen.findByRole("img", { name: /Kod QR odnośnika startowego @tc_alerts_bot/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /t\.me\/tc_alerts_bot\?start=abc123/ })).toBeInTheDocument();

    destinations.mockResolvedValue([OPERATOR, tapped]);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3100);
    });

    const done = await screen.findByText(/odbiera wiadomości od @tc_alerts_bot/);
    expect(within(done.closest("div") as HTMLElement).getByText("phone")).toBeInTheDocument();
  });
});
