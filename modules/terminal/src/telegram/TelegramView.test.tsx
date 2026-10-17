import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MarketDataError } from "../data/types";
import { TelegramView } from "./TelegramView";
import type { Assignment, Bot, Destination, GateState, Purpose, TelegramApi } from "./telegramApi";

/**
 * The tab from the operator's seat: that what nobody hears is the first thing said, that a purpose is assigned from its
 * row, that the account logs in through Telegram's steps, that a refusal stays in the dialog in the door's words, and that
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
  defaultAssignment: false,
  purposesUnheard: 1,
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

function purpose(overrides: Partial<Purpose> = {}): Purpose {
  return {
    name: "youtube.film.gold-talk",
    description: null,
    firstSeen: new Date("2026-10-01T10:00:00Z"),
    lastSeen: new Date("2026-10-02T10:00:00Z"),
    lastCaller: "the YouTube archive",
    destination: "operator",
    assignedBy: "youtube",
    ...overrides,
  };
}

function api(overrides: Partial<TelegramApi> = {}): TelegramApi {
  return {
    state: vi.fn(async () => LOGGED_IN),
    loginStart: vi.fn(),
    loginCode: vi.fn(),
    loginResend: vi.fn(),
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
    purposes: vi.fn(async () => [
      purpose(),
      purpose({ name: "social.post.trump", destination: null, assignedBy: null }),
    ]),
    assignments: vi.fn(
      async (): Promise<Assignment[]> => [{ key: "youtube", destination: "operator", bot: BOT.username, receives: true }],
    ),
    assign: vi.fn(),
    unassign: vi.fn(async () => undefined),
    ...overrides,
  };
}

afterEach(() => {
  vi.useRealTimers();
});

describe("TelegramView", () => {
  it("says at the top what nobody hears and offers to assign it, before any bot is opened", async () => {
    render(<TelegramView api={api()} />);

    expect(await screen.findByText(/nie ma odbiorcy — są zbierane, ale nikt o nich nie usłyszy/)).toBeInTheDocument();
    expect(screen.getByText("social.post.trump")).toBeInTheDocument();
    expect(screen.queryByText("youtube")).not.toBeInTheDocument();
  });

  it("shows only the bots until one is opened, and then who receives through it and what is sent there", async () => {
    render(<TelegramView api={api()} />);

    await userEvent.click(await screen.findByRole("button", { name: /@tc_alerts_bot/ }));

    expect(screen.getAllByText("@marek · Marek G.").length).toBeGreaterThan(0);
    expect(screen.getByRole("combobox", { name: "odbiorca dla youtube" })).toBeInTheDocument();
  });

  it("does not show the assignments of a bot that is not open", async () => {
    render(<TelegramView api={api()} />);

    await screen.findByRole("button", { name: /@tc_alerts_bot/ });

    expect(screen.queryByRole("combobox", { name: "odbiorca dla youtube" })).not.toBeInTheDocument();
  });

  it("assigns an unheard purpose from the top", async () => {
    const assign = vi.fn(async () => ({ key: "social.post.trump", destination: "operator", bot: BOT.username, receives: true }));
    render(<TelegramView api={api({ assign })} />);

    await userEvent.click(await screen.findByRole("button", { name: "Przypisz…" }));
    await userEvent.click(screen.getByRole("button", { name: "Przypisz" }));

    expect(assign).toHaveBeenCalledWith("social.post.trump", "operator", expect.anything());
  });

  it("keeps the door's reason in the dialog when it refuses to remove a bot that is still heard", async () => {
    const removeBot = vi
      .fn()
      .mockRejectedValue(new MarketDataError("refused", "@tc_alerts_bot still receives 'youtube'. Move those assignments first."));
    render(<TelegramView api={api({ removeBot })} />);

    await userEvent.click(await screen.findByRole("button", { name: /@tc_alerts_bot/ }));
    await userEvent.click(await screen.findByRole("button", { name: "Usuń bota @tc_alerts_bot" }));
    await userEvent.click(screen.getByRole("button", { name: "Usuń bota" }));

    expect(await screen.findByText(/still receives 'youtube'/)).toBeInTheDocument();
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
    await userEvent.type(screen.getByPlaceholderText("+48123456789"), "+48123456789");
    await userEvent.click(screen.getByRole("button", { name: "Wyślij kod" }));

    expect(await screen.findByText(/aplikacji Telegram zalogowanej na tym koncie/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Nie dostałem kodu/ }));

    expect(await screen.findByText(/Kod poszedł SMS-em/)).toBeInTheDocument();
    expect(loginResend).toHaveBeenCalledTimes(1);
  });

  it("does not offer another way when Telegram has none, and says where the code is instead", async () => {
    const loginStart = vi.fn(async () => ({ step: "code" as const, delivery: "app" as const, canResend: false }));
    render(<TelegramView api={api({ state: vi.fn(async () => LOGGED_OUT), loginStart })} />);

    await userEvent.click(await screen.findByRole("button", { name: "Zaloguj konto…" }));
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
    await userEvent.type(screen.getByPlaceholderText("+48123456789"), "+48111222333");
    await userEvent.click(screen.getByRole("button", { name: "Wyślij kod" }));
    await screen.findByLabelText(/Kod, który przyszedł/);
    first.unmount();

    render(<TelegramView api={api({ state: vi.fn(async () => LOGGED_OUT), loginStart })} />);
    await userEvent.click(await screen.findByRole("button", { name: "Zaloguj konto…" }));

    expect(screen.getByPlaceholderText("+48123456789")).toHaveValue("+48111222333");
    localStorage.removeItem("tc.telegram.ownerPhone");
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
          state: vi.fn(async () => ({ ...LOGGED_OUT, bots: 0, destinations: 0, destinationsReady: 0, purposesUnheard: 0 })),
          bots: vi.fn(async () => []),
          destinations: vi.fn(async () => []),
          purposes: vi.fn(async () => []),
          assignments: vi.fn(async () => []),
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

    await userEvent.click(await screen.findByRole("button", { name: /@tc_alerts_bot/ }));
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

    await user.click(await screen.findByRole("button", { name: /@tc_alerts_bot/ }));
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
