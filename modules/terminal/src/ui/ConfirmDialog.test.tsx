import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { ConfirmDialog } from "./ConfirmDialog";

/**
 * The behaviours every confirmation in the terminal inherits by being built on
 * this — `terminal-dialogs` spec. They are tested once, here, which is the whole
 * argument for the component existing: three copies of a dialog drift apart one
 * behaviour at a time, and the operator stops knowing what to expect.
 */

function Harness({
  onConfirm,
  onClosed = () => {},
}: {
  onConfirm(): void | Promise<void>;
  onClosed?(): void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Ask
      </button>
      {open && (
        <ConfirmDialog
          title="Delete everything?"
          confirmLabel="Delete"
          busyLabel="Deleting…"
          onConfirm={onConfirm}
          onClose={() => {
            setOpen(false);
            onClosed();
          }}
        >
          <p>This cannot be undone.</p>
        </ConfirmDialog>
      )}
    </>
  );
}

/** A promise held open, so "while the work is in flight" is a state a test can
 *  stand in rather than a race it has to win. */
function deferred() {
  let resolve!: () => void;
  let reject!: (cause: Error) => void;
  const promise = new Promise<void>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("ConfirmDialog", () => {
  it("asks in a dialog, and does nothing until the operator confirms", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(<Harness onConfirm={onConfirm} />);

    await user.click(screen.getByRole("button", { name: "Ask" }));

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("This cannot be undone.")).toBeInTheDocument();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("backing out does nothing and leaves the view as it was", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(<Harness onConfirm={onConfirm} />);

    await user.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("closes once the confirmed work succeeds", async () => {
    const user = userEvent.setup();
    render(<Harness onConfirm={async () => {}} />);

    await user.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: "Delete" }));

    expect(await screen.findByRole("button", { name: "Ask" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("stays open while the work runs and will not start it twice", async () => {
    const user = userEvent.setup();
    const held = deferred();
    const onConfirm = vi.fn(() => held.promise);
    render(<Harness onConfirm={onConfirm} />);

    await user.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: "Delete" }));

    const working = await screen.findByRole("button", { name: "Deleting…" });
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(working).toBeDisabled();

    // A second click on a disabled button is a no-op — asserted rather than
    // assumed, because the double-submit is what this prevents.
    await user.click(working);
    expect(onConfirm).toHaveBeenCalledTimes(1);

    held.resolve();
    await screen.findByRole("button", { name: "Ask" });
  });

  it("keeps a failure inside the dialog, with the question still on screen", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn().mockRejectedValue(new Error("the archive refused"));
    const onClosed = vi.fn();
    render(<Harness onConfirm={onConfirm} onClosed={onClosed} />);

    await user.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: "Delete" }));

    expect(await screen.findByText("the archive refused")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(onClosed).not.toHaveBeenCalled();

    // And trying again is still on the table.
    onConfirm.mockResolvedValueOnce(undefined);
    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(await screen.findByRole("button", { name: "Ask" })).toBeInTheDocument();
  });

  it("Escape backs out, but not while the work is in flight", async () => {
    const user = userEvent.setup();
    const held = deferred();
    render(<Harness onConfirm={() => held.promise} />);

    await user.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: "Delete" }));
    await screen.findByRole("button", { name: "Deleting…" });

    await user.keyboard("{Escape}");
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    held.resolve();
    await screen.findByRole("button", { name: "Ask" });
  });

  it("Escape closes a dialog that is only asking", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(<Harness onConfirm={onConfirm} />);

    await user.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByRole("dialog");

    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("keeps the keyboard inside it while it is open", async () => {
    const user = userEvent.setup();
    render(<Harness onConfirm={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "Ask" }));
    const dialog = await screen.findByRole("dialog");

    // Opening takes the keyboard with it, so the first Tab lands inside.
    expect(dialog).toHaveFocus();

    // Round and round the dialog's own stops — never back to the page beneath,
    // whose "Ask" button is the one thing that would prove the trap leaks.
    for (let i = 0; i < 5; i++) {
      await user.tab();
      expect(dialog).toContainElement(document.activeElement as HTMLElement);
    }

    await user.tab({ shift: true });
    expect(dialog).toContainElement(document.activeElement as HTMLElement);
  });

  it("hands focus back to whatever opened it", async () => {
    const user = userEvent.setup();
    render(<Harness onConfirm={vi.fn()} />);

    const opener = screen.getByRole("button", { name: "Ask" });
    await user.click(opener);
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(await screen.findByRole("button", { name: "Ask" })).toHaveFocus();
  });
});
