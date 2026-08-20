import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AccountsView } from "./AccountsView";
import type { AccountsApi, AccountPosition, DemoAccount } from "./accountsApi";
import { MarketDataError } from "../data/types";

function account(overrides: Partial<DemoAccount> = {}): DemoAccount {
  return {
    id: "a1",
    name: "EUR",
    currency: "EUR",
    balance: 51000,
    available: 50800,
    pnl: -12.5,
    active: true,
    ...overrides,
  };
}

function position(overrides: Partial<AccountPosition> = {}): AccountPosition {
  return {
    id: "p1",
    symbol: "US100",
    direction: "BUY",
    size: 0.5,
    openLevel: 21000,
    pnl: 12.25,
    currency: "EUR",
    ...overrides,
  };
}

/** The module as this screen sees it: rows a test can move, and failures it can arm. */
function fakeApi() {
  const state = {
    accounts: [account(), account({ id: "a2", name: "demo2", active: false, balance: 9000 })],
    positions: [position()],
    accountsFailure: null as Error | null,
    positionsFailure: null as Error | null,
    topUpFailure: null as Error | null,
    switchFailure: null as Error | null,
    switched: [] as string[],
    toppedUp: [] as number[],
  };

  const api: AccountsApi = {
    async listAccounts() {
      if (state.accountsFailure) throw state.accountsFailure;
      return state.accounts;
    },
    async listPositions() {
      if (state.positionsFailure) throw state.positionsFailure;
      return state.positions;
    },
    async switchAccount(accountId) {
      if (state.switchFailure) throw state.switchFailure;
      state.switched.push(accountId);
      state.accounts = state.accounts.map((row) => ({ ...row, active: row.id === accountId }));
      state.positions = [];
      return state.accounts.find((row) => row.id === accountId)!;
    },
    async topUp(amount) {
      if (state.topUpFailure) throw state.topUpFailure;
      state.toppedUp.push(amount);
      state.accounts = state.accounts.map((row) =>
        row.active ? { ...row, balance: row.balance + amount } : row,
      );
      return state.accounts.find((row) => row.active)!;
    },
  };

  return { api, state };
}

afterEach(() => {
  vi.useRealTimers();
});

describe("AccountsView", () => {
  it("shows the demo accounts, which one is traded, and what is open on it", async () => {
    // `terminal-accounts` spec, "Operator otwiera ekran"
    const { api } = fakeApi();
    render(<AccountsView api={api} />);

    expect(await screen.findByText("51000.00")).toBeInTheDocument();
    expect(screen.getByText("demo2")).toBeInTheDocument();
    expect(screen.getByText("active")).toBeInTheDocument();
    // The positions are named as the active account's, not as "everything open".
    expect(screen.getByText(/on EUR, the account being traded/i)).toBeInTheDocument();
    expect(screen.getByText("US100")).toBeInTheDocument();
  });

  it("picks up a change without the operator asking for one", async () => {
    // `terminal-accounts` spec, "Stan zmienia się bez działania operatora"
    vi.useFakeTimers();
    const { api, state } = fakeApi();
    render(<AccountsView api={api} />);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByText("51000.00")).toBeInTheDocument();

    state.accounts = [account({ balance: 61000 }), ...state.accounts.slice(1)];
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    expect(screen.getByText("61000.00")).toBeInTheDocument();
  });

  it("says a failed read failed, and keeps the last answer rather than blanking it", async () => {
    // `terminal-accounts` spec, "Odczyt zawiódł" — an empty table would read as an
    // account with nothing on it.
    vi.useFakeTimers();
    const { api, state } = fakeApi();
    render(<AccountsView api={api} />);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByText("51000.00")).toBeInTheDocument();

    state.accountsFailure = new Error("network blip");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    expect(screen.getByText(/accounts could not be read/i)).toBeInTheDocument();
    expect(screen.getByText("51000.00")).toBeInTheDocument();
  });

  it("adds funds and shows the balance after the move", async () => {
    // `terminal-accounts` spec, "Dołożenie środków"
    const user = userEvent.setup();
    const { api, state } = fakeApi();
    render(<AccountsView api={api} />);
    await screen.findByText("51000.00");

    await user.click(screen.getByRole("button", { name: /add funds/i }));
    const amount = screen.getByLabelText("Amount");
    await user.clear(amount);
    await user.type(amount, "2500");
    await user.click(screen.getByRole("button", { name: "Apply" }));

    await waitFor(() => expect(state.toppedUp).toEqual([2500]));
    expect(await screen.findByText("53500.00")).toBeInTheDocument();
  });

  it("takes funds away when the amount is negative", async () => {
    const user = userEvent.setup();
    const { api, state } = fakeApi();
    render(<AccountsView api={api} />);
    await screen.findByText("51000.00");

    await user.click(screen.getByRole("button", { name: /add funds/i }));
    const amount = screen.getByLabelText("Amount");
    await user.clear(amount);
    await user.type(amount, "-1000");
    await user.click(screen.getByRole("button", { name: "Apply" }));

    await waitFor(() => expect(state.toppedUp).toEqual([-1000]));
  });

  it("says why a refused top-up was refused, and leaves the balance alone", async () => {
    // `terminal-accounts` spec, "Moduł odmawia korekty"
    const user = userEvent.setup();
    const { api, state } = fakeApi();
    state.topUpFailure = new MarketDataError("refused", "top up balance exceeded");
    render(<AccountsView api={api} />);
    await screen.findByText("51000.00");

    await user.click(screen.getByRole("button", { name: /add funds/i }));
    await user.click(screen.getByRole("button", { name: "Apply" }));

    expect(await screen.findByText(/top up balance exceeded/i)).toBeInTheDocument();
    expect(screen.getByText("51000.00")).toBeInTheDocument();
  });

  it("warns that switching ends the quote stream before it switches", async () => {
    // `terminal-accounts` spec, "Operator przełącza konto" — the cost lands in the
    // archive, which this screen does not show.
    const user = userEvent.setup();
    const { api, state } = fakeApi();
    render(<AccountsView api={api} />);
    await screen.findByText("demo2");

    await user.click(screen.getByRole("button", { name: /make active/i }));

    expect(screen.getByText(/ends the provider's quote stream/i)).toBeInTheDocument();
    expect(state.switched).toEqual([]);

    await user.click(screen.getByRole("button", { name: "Switch" }));

    await waitFor(() => expect(state.switched).toEqual(["a2"]));
    expect(await screen.findByText(/on demo2, the account being traded/i)).toBeInTheDocument();
  });

  it("leaves the active account alone when the switch is refused", async () => {
    // `terminal-accounts` spec, "Przełączenie odmówione"
    const user = userEvent.setup();
    const { api, state } = fakeApi();
    state.switchFailure = new MarketDataError("refused", "capital.com would not switch");
    render(<AccountsView api={api} />);
    await screen.findByText("demo2");

    await user.click(screen.getByRole("button", { name: /make active/i }));
    await user.click(screen.getByRole("button", { name: "Switch" }));

    expect(await screen.findByText(/would not switch/i)).toBeInTheDocument();
    expect(screen.getByText(/on EUR, the account being traded/i)).toBeInTheDocument();
  });
});
