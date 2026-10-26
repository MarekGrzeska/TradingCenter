import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { BackButton } from "./BackButton";

it("names where it goes and goes there", async () => {
  const onClick = vi.fn();
  render(<BackButton label="Catalogue" onClick={onClick} />);
  await userEvent.click(screen.getByRole("button", { name: "← Catalogue" }));
  expect(onClick).toHaveBeenCalledOnce();
});
