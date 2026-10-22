import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MarketDataError } from "../data/types";
import { PromptsPanel } from "./PromptsPanel";
import type { Prompt, YoutubeApi } from "./youtubeApi";

/** The Prompts section of the YouTube tab from the operator's seat: what each prompt says about who reads by it, and that a refusal stays in view. */

const SEEDED: Prompt = {
  id: 1,
  name: "Rynkowy",
  seeded: true,
  version: 2,
  body: "Streszcz film dla tradera.",
  createdAt: new Date("2026-10-22T09:00:00Z"),
  updatedAt: new Date("2026-10-22T10:00:00Z"),
  channels: [],
  topics: [],
};
const TECHNICAL: Prompt = {
  ...SEEDED,
  id: 2,
  name: "Technical",
  seeded: false,
  version: 1,
  body: "Levels only.",
  channels: ["Sim Złoto PL"],
  topics: ["bitcoin"],
};

function api(overrides: Partial<YoutubeApi> = {}): YoutubeApi {
  return {
    prompts: vi.fn(async () => ({ prompts: [SEEDED, TECHNICAL], maxChars: 8000, ceiling: 50 })),
    createPrompt: vi.fn(),
    updatePrompt: vi.fn(),
    deletePrompt: vi.fn(async () => undefined),
    ...overrides,
  } as unknown as YoutubeApi;
}

describe("PromptsPanel", () => {
  it("lists the prompts with their version and who reads by each, and offers no delete for the seeded one", async () => {
    render(<PromptsPanel client={api()} />);

    const seeded = (await screen.findByText("Rynkowy")).closest("li")!;
    const technical = screen.getByText("Technical").closest("li")!;

    expect(within(seeded).getByText("v2")).toBeInTheDocument();
    expect(within(seeded).getByText("domyślny")).toBeInTheDocument();
    expect(within(seeded).queryByRole("button", { name: "Usuń" })).not.toBeInTheDocument();
    expect(within(technical).getByText(/kanały: Sim Złoto PL · tematy: bitcoin/)).toBeInTheDocument();
  });

  it("sends only what changed when a prompt is edited", async () => {
    const client = api({ updatePrompt: vi.fn(async () => TECHNICAL) });
    render(<PromptsPanel client={client} />);

    const technical = (await screen.findByText("Technical")).closest("li")!;
    await userEvent.click(within(technical).getByRole("button", { name: "Edytuj" }));
    const text = screen.getByRole("textbox", { name: /Co model ma znaleźć/ });
    await userEvent.clear(text);
    await userEvent.type(text, "Levels and volume.");
    await userEvent.click(screen.getByRole("button", { name: "Zapisz" }));

    expect(client.updatePrompt).toHaveBeenCalledWith(2, { body: "Levels and volume." }, expect.anything());
  });

  it("keeps the module's reason in the dialog when it refuses to delete", async () => {
    const deletePrompt = vi.fn().mockRejectedValue(new MarketDataError("refused", "'Technical' is still read by channel Sim Złoto PL"));
    render(<PromptsPanel client={api({ deletePrompt })} />);

    const technical = (await screen.findByText("Technical")).closest("li")!;
    await userEvent.click(within(technical).getByRole("button", { name: "Usuń" }));
    await userEvent.click(screen.getAllByRole("button", { name: "Usuń" }).at(-1)!);

    expect(await screen.findByText(/is still read by channel Sim Złoto PL/)).toBeInTheDocument();
  });
});
