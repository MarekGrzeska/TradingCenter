import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Autocomplete } from "./Autocomplete";
import {
  archivedInstrumentSource,
  assetClassSource,
  instrumentInClassSource,
} from "./autocompleteSources";
import type { ArchiveAdmin, InstrumentSource } from "../data/source";
import type { AssetClass, Instrument, TrackedPair } from "../data/types";
import type { ArchivedInstrument } from "./autocompleteSources";

function fakeInstrumentSource(overrides: Partial<InstrumentSource> = {}): InstrumentSource {
  return {
    id: "gateway",
    label: "capital-gateway",
    whenUnreachable: "instrument search is unavailable",
    ping: vi.fn(async () => {}),
    searchInstruments: vi.fn(async () => []),
    listInstruments: vi.fn(async () => ({ instruments: [], count: 0, truncated: false })),
    listAssetClasses: vi.fn(async () => []),
    ...overrides,
  };
}

function fakeArchiveAdmin(overrides: Partial<ArchiveAdmin> = {}): ArchiveAdmin {
  return {
    listPairs: vi.fn(async () => []),
    trackPairs: vi.fn(async () => ({ results: [], jobId: null })),
    untrackPair: vi.fn(async () => {}),
    coverage: vi.fn(async () => ({
      symbol: "",
      resolution: "MINUTE" as const,
      ranges: [],
      earliestReachable: null,
    })),
    estimateJob: vi.fn(async () => ({ pairs: [], totalEstimatedCandles: 0, totalEstimatedBytes: 0 })),
    listJobs: vi.fn(async () => []),
    readJob: vi.fn(),
    retryJob: vi.fn(),
    ...overrides,
  };
}

function trackedPair(symbol: string, resolution: TrackedPair["resolution"]): TrackedPair {
  return {
    symbol,
    resolution,
    addedAt: 0,
    collectFrom: 0,
    latestCandle: null,
    collection: "collecting",
  };
}

/** A minimal string-keyed source, for the behavior every use of the component
 *  shares regardless of what it is picking. */
function stringSource(options: string[], opts: { truncated?: boolean } = {}) {
  return vi.fn(async (query: string) => ({
    options: query ? options.filter((o) => o.toLowerCase().includes(query.toLowerCase())) : options,
    truncated: opts.truncated ?? false,
  }));
}

function renderPicker(
  props: Partial<React.ComponentProps<typeof Autocomplete<string>>> = {},
) {
  const onChange = vi.fn();
  const source = props.source ?? stringSource(["Alpha", "Beta", "Gamma"]);
  render(
    <Autocomplete<string>
      value={null}
      onChange={onChange}
      source={source}
      getOptionId={(o) => o}
      getOptionLabel={(o) => o}
      ariaLabel="Pick one"
      {...props}
    />,
  );
  return { onChange, source };
}

describe("Autocomplete: keyboard", () => {
  it("picks the first, already-highlighted option on Enter alone", async () => {
    const user = userEvent.setup();
    const { onChange } = renderPicker();

    await user.click(screen.getByRole("combobox"));
    await waitFor(() => expect(screen.getByRole("option", { name: "Alpha" })).toBeInTheDocument());

    await user.keyboard("{Enter}");

    expect(onChange).toHaveBeenCalledWith("Alpha");
  });

  it("moves the highlight with ArrowDown before Enter picks it", async () => {
    const user = userEvent.setup();
    const { onChange } = renderPicker();

    await user.click(screen.getByRole("combobox"));
    await waitFor(() => expect(screen.getByRole("option", { name: "Alpha" })).toBeInTheDocument());

    await user.keyboard("{ArrowDown}{ArrowDown}{Enter}");

    expect(onChange).toHaveBeenCalledWith("Gamma");
  });

  it("does not move highlight above the first option", async () => {
    const user = userEvent.setup();
    const { onChange } = renderPicker();

    await user.click(screen.getByRole("combobox"));
    await waitFor(() => expect(screen.getByRole("option", { name: "Alpha" })).toBeInTheDocument());

    await user.keyboard("{ArrowUp}{Enter}");

    expect(onChange).toHaveBeenCalledWith("Alpha");
  });

  it("closes suggestions on Escape and leaves the prior choice untouched", async () => {
    const user = userEvent.setup();
    const { onChange } = renderPicker();

    await user.click(screen.getByRole("combobox"));
    await waitFor(() => expect(screen.getByRole("option", { name: "Alpha" })).toBeInTheDocument());

    await user.keyboard("{Escape}");

    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe("Autocomplete: states", () => {
  it("says plainly that nothing matched, rather than an empty list", async () => {
    renderPicker({ source: stringSource([]) });

    await userEvent.setup().click(screen.getByRole("combobox"));
    await userEvent.setup().type(screen.getByRole("combobox"), "zzz");

    expect(await screen.findByText("No matches.")).toBeInTheDocument();
  });

  it("names a source failure and offers a retry that re-issues the fetch", async () => {
    const source = vi
      .fn()
      .mockRejectedValueOnce(new Error("gateway unreachable"))
      .mockResolvedValueOnce({ options: ["Alpha"] });
    const user = userEvent.setup();
    renderPicker({ source });

    await user.click(screen.getByRole("combobox"));
    expect(await screen.findByText("gateway unreachable")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Retry" }));

    await waitFor(() => expect(screen.getByRole("option", { name: "Alpha" })).toBeInTheDocument());
  });

  it("says when the list was cut short, and that typing narrows it further", async () => {
    renderPicker({ source: stringSource(["Alpha"], { truncated: true }) });

    await userEvent.setup().click(screen.getByRole("combobox"));

    expect(await screen.findByText(/cut short/)).toBeInTheDocument();
  });
});

function ControlledPicker() {
  const [value, setValue] = useState<string | null>("Alpha");
  return (
    <Autocomplete<string>
      value={value}
      onChange={setValue}
      source={stringSource(["Alpha", "Beta"])}
      getOptionId={(o) => o}
      getOptionLabel={(o) => o}
      ariaLabel="Pick one"
    />
  );
}

describe("Autocomplete: made choice", () => {
  it("shows the current selection and clears it without an input remount losing state", async () => {
    render(<ControlledPicker />);

    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole("button", { name: "Clear Pick one" }));

    expect(screen.getByRole("combobox")).toBeInTheDocument();
  });
});

// The three real sources the terminal builds this component with. Same
// keyboard path through all three proves the promise in design.md, "Terminal:
// jeden `Autocomplete`, trzy źródła" — the component does not know which one
// it was given.
describe("Autocomplete: identical keyboard behavior across all three real sources", () => {
  it("asset classes", async () => {
    const gateway = fakeInstrumentSource({
      listAssetClasses: vi.fn(async () => ["CRYPTO", "INDICES"] as AssetClass[]),
    });
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <Autocomplete<AssetClass>
        value={null}
        onChange={onChange}
        source={assetClassSource(gateway)}
        getOptionId={(c) => c}
        getOptionLabel={(c) => c}
        ariaLabel="Asset class"
      />,
    );

    await user.click(screen.getByRole("combobox"));
    await waitFor(() => expect(screen.getByRole("option", { name: "CRYPTO" })).toBeInTheDocument());
    await user.keyboard("{ArrowDown}{Enter}");

    expect(onChange).toHaveBeenCalledWith("INDICES");
  });

  it("instruments in a class", async () => {
    const btc: Instrument = {
      symbol: "BTCUSD",
      name: "Bitcoin",
      assetClass: "CRYPTO",
      tradeable: true,
      bid: 1,
      ask: 2,
    };
    const eth: Instrument = {
      symbol: "ETHUSD",
      name: "Ether",
      assetClass: "CRYPTO",
      tradeable: true,
      bid: 3,
      ask: 4,
    };
    const gateway = fakeInstrumentSource({
      listInstruments: vi.fn(async () => ({ instruments: [btc, eth], count: 2, truncated: false })),
    });
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <Autocomplete<Instrument>
        value={null}
        onChange={onChange}
        source={instrumentInClassSource(gateway, "CRYPTO")}
        getOptionId={(i) => i.symbol}
        getOptionLabel={(i) => i.symbol}
        ariaLabel="Instrument"
      />,
    );

    await user.click(screen.getByRole("combobox"));
    await waitFor(() => expect(screen.getByRole("option", { name: "BTCUSD" })).toBeInTheDocument());
    await user.keyboard("{ArrowDown}{Enter}");

    expect(onChange).toHaveBeenCalledWith(eth);
  });

  it("archived instruments", async () => {
    const archive = fakeArchiveAdmin({
      listPairs: vi.fn(async () => [trackedPair("US100", "MINUTE")]),
    });
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <Autocomplete<ArchivedInstrument>
        value={null}
        onChange={onChange}
        source={archivedInstrumentSource(archive)}
        getOptionId={(a) => a.symbol}
        getOptionLabel={(a) => a.symbol}
        ariaLabel="Archived instrument"
      />,
    );

    await user.click(screen.getByRole("combobox"));
    await waitFor(() => expect(screen.getByRole("option", { name: "US100" })).toBeInTheDocument());
    await user.keyboard("{ArrowDown}{Enter}");

    expect(onChange).toHaveBeenCalledWith({ symbol: "US100", resolutions: ["MINUTE"] });
  });
});
