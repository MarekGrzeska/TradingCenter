import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MarketDataError } from "../data/types";
import { SettingsPanel } from "./SettingsPanel";
import type { LoopSettings, YoutubeApi } from "./youtubeApi";

/** The Settings section of the YouTube tab: that a save sends what the operator typed, and that a refusal stays in view. */

const STANDING: LoopSettings = {
  pollIntervalMinutes: 30,
  topicIntervalMinutes: 360,
  topicMaxVideos: 3,
  saved: false,
  pollIntervalRange: [5, 1440],
  topicIntervalRange: [15, 10080],
  topicMaxVideosRange: [1, 20],
};

function api(overrides: Partial<YoutubeApi> = {}): YoutubeApi {
  return {
    settings: vi.fn(async () => STANDING),
    updateSettings: vi.fn(async () => ({ ...STANDING, saved: true })),
    ...overrides,
  } as unknown as YoutubeApi;
}

describe("SettingsPanel", () => {
  it("shows what stands, says nothing has been saved, and saves the three numbers as typed", async () => {
    const client = api();
    render(<SettingsPanel client={client} />);

    const poll = await screen.findByRole("textbox", { name: /minut między przebiegami/ });
    expect(poll).toHaveValue("30");
    expect(screen.getByText(/Nic jeszcze nie zapisano/)).toBeInTheDocument();
    await userEvent.clear(poll);
    await userEvent.type(poll, "10");
    await userEvent.click(screen.getByRole("button", { name: "Zapisz" }));

    expect(client.updateSettings).toHaveBeenCalledWith(
      { pollIntervalMinutes: 10, topicIntervalMinutes: 360, topicMaxVideos: 3 },
      expect.anything(),
    );
  });

  it("keeps the module's reason on screen when it refuses the values", async () => {
    const updateSettings = vi.fn().mockRejectedValue(new MarketDataError("refused", "the loop passes every 5 to 1440 minutes"));
    render(<SettingsPanel client={api({ updateSettings })} />);

    const poll = await screen.findByRole("textbox", { name: /minut między przebiegami/ });
    await userEvent.clear(poll);
    await userEvent.type(poll, "1");
    await userEvent.click(screen.getByRole("button", { name: "Zapisz" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("the loop passes every 5 to 1440 minutes");
  });

  it("does not offer a save until something changed, and refuses a non-number before asking the module", async () => {
    const client = api();
    render(<SettingsPanel client={client} />);

    const save = await screen.findByRole("button", { name: "Zapisz" });
    expect(save).toBeDisabled();
    const max = screen.getByRole("textbox", { name: /filmów z jednego wyszukiwania/ });
    await userEvent.clear(max);
    await userEvent.type(max, "dużo");
    await userEvent.click(save);

    expect(await screen.findByRole("alert")).toHaveTextContent("liczbą całkowitą");
    expect(client.updateSettings).not.toHaveBeenCalled();
  });
});
