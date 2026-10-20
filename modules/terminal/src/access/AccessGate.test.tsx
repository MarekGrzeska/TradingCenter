import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AccessGate } from "./AccessGate";
import type { AccessApi } from "./accessApi";

const answering = (roles: string[]): AccessApi => ({
  me: vi.fn(async () => ({ roles, person: "p" })),
});

describe("AccessGate", () => {
  it("shows the terminal to an admin", async () => {
    render(
      <AccessGate api={answering(["admin"])}>
        <p>the terminal</p>
      </AccessGate>,
    );
    expect(await screen.findByText("the terminal")).toBeInTheDocument();
  });

  it("shows a viewer a page that says so, and none of the terminal", async () => {
    render(
      <AccessGate api={answering(["viewer"])}>
        <p>the terminal</p>
      </AccessGate>,
    );
    expect(await screen.findByText("No access to the terminal")).toBeInTheDocument();
    expect(screen.queryByText("the terminal")).not.toBeInTheDocument();
  });

  it("lets the terminal render when the workbench cannot be asked", async () => {
    const down: AccessApi = {
      me: vi.fn(async () => {
        throw new Error("down");
      }),
    };
    render(
      <AccessGate api={down}>
        <p>the terminal</p>
      </AccessGate>,
    );
    expect(await screen.findByText("the terminal")).toBeInTheDocument();
  });
});
