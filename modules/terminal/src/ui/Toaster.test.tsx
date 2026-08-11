import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { Toaster } from "./Toaster";
import { toastStore } from "./toastStore";

afterEach(() => act(() => toastStore.clear()));

describe("Toaster", () => {
  it("renders nothing at all when there is nothing to say", () => {
    const { container } = render(<Toaster />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the title and the detail, because the detail is the part nobody can guess", () => {
    render(<Toaster />);
    act(() =>
      toastStore.show({
        key: "a",
        severity: "error",
        title: "US100 · indicators unavailable",
        detail: "no MINUTE_5 series collected for 'US100'",
      }),
    );

    expect(screen.getByText("US100 · indicators unavailable")).toBeInTheDocument();
    expect(screen.getByText(/no MINUTE_5 series collected/)).toBeInTheDocument();
  });

  it("announces an error as an alert and anything else as a status", () => {
    render(<Toaster />);
    act(() => toastStore.show({ key: "a", severity: "error", title: "Broken" }));
    act(() => toastStore.show({ key: "b", severity: "info", title: "Saved" }));

    expect(screen.getByRole("alert")).toHaveTextContent("Broken");
    expect(screen.getByRole("status")).toHaveTextContent("Saved");
  });

  it("can be dismissed, and says which one the button dismisses", async () => {
    const user = userEvent.setup();
    render(<Toaster />);
    act(() => toastStore.show({ key: "a", severity: "error", title: "Broken" }));

    await user.click(screen.getByRole("button", { name: "Dismiss: Broken" }));

    expect(screen.queryByText("Broken")).not.toBeInTheDocument();
  });

  it("never announces itself as a dialog — it takes no focus and blocks nothing", () => {
    render(<Toaster />);
    act(() => toastStore.show({ key: "a", severity: "error", title: "Broken" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.activeElement).toBe(document.body);
  });
});
