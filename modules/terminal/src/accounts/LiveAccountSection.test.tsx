import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { LiveAccountSection } from "./LiveAccountSection";
import type { CloseAllItem, LiveAccountApi } from "./liveAccountApi";

function fakeLive(outcome: CloseAllItem[]) {
  const state = { closed: 0, positions: 2 };
  const api: LiveAccountApi = {
    async listAccounts() {
      return [
        { id: "L1", name: "Live", currency: "USD", balance: 1000, available: 900, pnl: 3, active: true },
      ];
    },
    async listPositions() {
      return Array.from({ length: state.positions }, (_, i) => ({
        id: `p${i + 1}`,
        symbol: "US100",
        direction: "BUY",
        size: 0.1,
        openLevel: 25000,
        pnl: 1,
        currency: "USD",
      }));
    },
    async listWorkingOrders() {
      return [];
    },
    async closeAll() {
      state.closed += 1;
      state.positions = 0;
      return outcome;
    },
  };
  return { api, state };
}

const CLOSED: CloseAllItem[] = [
  { kind: "position", id: "p1", symbol: "US100", status: "CLOSED", reason: null },
  { kind: "position", id: "p2", symbol: "US100", status: "CLOSED", reason: null },
];

describe("LiveAccountSection", () => {
  it("closes everything after a question that says it is real money and how much", async () => {
    // `terminal-accounts` spec, "Operator zamyka wszystko"
    const user = userEvent.setup();
    const { api, state } = fakeLive(CLOSED);
    render(<LiveAccountSection api={api} pollMs={5000} />);
    await screen.findAllByText("US100");

    await user.click(screen.getByRole("button", { name: "Close everything" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/real money/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/2 positions/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Close everything" }));

    expect(state.closed).toBe(1);
    expect(await screen.findByText(/position p1 \(US100\): CLOSED/)).toBeInTheDocument();
    expect(await screen.findByText("nothing open on the live account")).toBeInTheDocument();
  });

  it("sends nothing when the operator backs out", async () => {
    // `terminal-accounts` spec, "Operator rezygnuje przy potwierdzeniu"
    const user = userEvent.setup();
    const { api, state } = fakeLive(CLOSED);
    render(<LiveAccountSection api={api} pollMs={5000} />);
    await screen.findAllByText("US100");

    await user.click(screen.getByRole("button", { name: "Close everything" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }));

    expect(state.closed).toBe(0);
  });

  it("names a position it could not close, and why", async () => {
    // `terminal-accounts` spec, "Część pozycji nie zamknięta"
    const user = userEvent.setup();
    const { api } = fakeLive([
      CLOSED[0],
      { kind: "position", id: "p2", symbol: "US100", status: "REJECTED", reason: "error.market.closed" },
    ]);
    render(<LiveAccountSection api={api} pollMs={5000} />);
    await screen.findAllByText("US100");

    await user.click(screen.getByRole("button", { name: "Close everything" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Close everything" }));

    expect(await screen.findByText(/position p2 \(US100\): REJECTED — error.market.closed/)).toBeInTheDocument();
  });
});
