import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MarketDataError } from "../data/types";
import { formatInstant, formatUtcInstant } from "../ui/formatTime";
import { SchedulesPanel } from "./SchedulesPanel";
import type { Schedule, ScheduleFire, TeamRevision, TeamsApi, Trigger } from "./teamsApi";

const REVISION: TeamRevision = {
  id: 9,
  teamId: 1,
  version: 2,
  definition: {
    agents: [],
    dependencies: [],
    limits: { runLimit: null, dailyLimit: null },
    trading: { maxOrderSize: null, ordersPerRun: null, ordersPerDay: null },
  },
  createdAt: 1_760_000_000,
};

const SCHEDULE: Schedule = {
  id: 11,
  teamId: 1,
  revisionMode: "pinned",
  pinnedRevisionId: 9,
  cronExpression: "*/5 * * * *",
  nextFireAt: 1_755_374_700, // 2025-08-16T20:05:00Z
  enabled: true,
  disabledReason: null,
  consecutiveFailures: 0,
  unattendedAck: false,
  createdAt: 1_760_000_000,
  updatedAt: 1_760_000_000,
};

const TRIGGER: Trigger = {
  id: 21,
  teamId: 1,
  revisionMode: "latest",
  pinnedRevisionId: null,
  toolName: "read_indicators",
  arguments: { symbol: "US100" },
  fieldPath: "rsi",
  comparison: "gt",
  threshold: "70.00000000",
  cooldownSeconds: 900,
  pollIntervalSeconds: 300,
  nextCheckAt: 1_760_000_300,
  lastResult: null,
  lastCheckedAt: null,
  lastFiredAt: null,
  enabled: true,
  disabledReason: null,
  consecutiveFailures: 0,
  unattendedAck: false,
  createdAt: 1_760_000_000,
  updatedAt: 1_760_000_000,
};

/** The schedule row's own `<li>` — both sections render an "Edit"/"Disable"/"History"
 *  button, so a test after the schedule specifically has to scope to it. */
async function scheduleRow(): Promise<HTMLElement> {
  const cron = await screen.findByText(SCHEDULE.cronExpression);
  const li = cron.closest("li");
  if (li === null) throw new Error("schedule row not found");
  return li;
}

function fakeApi(overrides: Partial<TeamsApi> = {}): TeamsApi {
  return {
    listModels: vi.fn(async () => []),
    listTools: vi.fn(async () => [
      { name: "read_indicators", description: "reads indicators", readOnly: true },
    ]),
    listTeams: vi.fn(async () => []),
    createTeam: vi.fn(async () => {
      throw new Error("not stubbed");
    }),
    getTeam: vi.fn(async () => {
      throw new Error("not stubbed");
    }),
    latestRevision: vi.fn(async () => REVISION),
    getRevision: vi.fn(async () => REVISION),
    revisionById: vi.fn(async () => REVISION),
    saveRevision: vi.fn(async () => REVISION),
    archiveTeam: vi.fn(async () => {}),
    layout: vi.fn(async () => new Map()),
    saveLayout: vi.fn(async () => {}),
    startRun: vi.fn(async () => {
      throw new Error("not stubbed");
    }),
    listRuns: vi.fn(async () => []),
    getRun: vi.fn(async () => {
      throw new Error("not stubbed");
    }),
    runSteps: vi.fn(async () => []),
    runToolCalls: vi.fn(async () => []),
    runTrades: vi.fn(async () => []),
    cancelRun: vi.fn(async () => {
      throw new Error("not stubbed");
    }),
    watchRun: vi.fn(async () => {
      throw new Error("not stubbed");
    }),
    listSchedules: vi.fn(async () => [SCHEDULE]),
    createSchedule: vi.fn(async () => SCHEDULE),
    updateSchedule: vi.fn(async () => SCHEDULE),
    enableSchedule: vi.fn(async () => ({ ...SCHEDULE, enabled: true, disabledReason: null })),
    disableSchedule: vi.fn(async () => ({ ...SCHEDULE, enabled: false })),
    scheduleFires: vi.fn(async () => []),
    nextFires: vi.fn(async () => []),
    listTriggers: vi.fn(async () => [TRIGGER]),
    createTrigger: vi.fn(async () => TRIGGER),
    updateTrigger: vi.fn(async () => TRIGGER),
    enableTrigger: vi.fn(async () => ({ ...TRIGGER, enabled: true, disabledReason: null })),
    disableTrigger: vi.fn(async () => ({ ...TRIGGER, enabled: false })),
    triggerFires: vi.fn(async () => []),
    ...overrides,
  };
}

describe("a schedule's next fire", () => {
  it("shows the module's own timestamp in UTC and in the terminal's local time — never recomputed", async () => {
    const api = fakeApi();
    render(<SchedulesPanel api={api} teamId={1} teamName="Morning desk" tools={[]} onClose={vi.fn()} onWatchRun={vi.fn()} />);

    // Both readings of the exact same instant the module answered with — nothing here
    // parses `*/5 * * * *` to produce them.
    expect(await screen.findByText(new RegExp(formatUtcInstant(SCHEDULE.nextFireAt)))).toBeInTheDocument();
    expect(screen.getByText(new RegExp(formatInstant(SCHEDULE.nextFireAt)))).toBeInTheDocument();
  });

  it("previews the next several fires from the module when a schedule is opened, not from a local parser", async () => {
    // Deliberately not slots `*/5 * * * *` would ever land on, so a passing test proves
    // the value came from `nextFires` and not from a parser reimplemented here.
    const oddTimes = [1_755_000_037, 1_755_000_911];
    const api = fakeApi({ nextFires: vi.fn(async () => oddTimes) });
    render(<SchedulesPanel api={api} teamId={1} teamName="Morning desk" tools={[]} onClose={vi.fn()} onWatchRun={vi.fn()} />);

    await userEvent.click(within(await scheduleRow()).getByRole("button", { name: "Edit" }));

    await waitFor(() => expect(api.nextFires).toHaveBeenCalledWith(SCHEDULE.id, 5, expect.anything()));
    for (const t of oddTimes) {
      expect(await screen.findByText(new RegExp(formatUtcInstant(t)))).toBeInTheDocument();
    }
  });
});

describe("creating and editing a schedule", () => {
  it("posts the draft and reloads the list", async () => {
    const api = fakeApi({ listSchedules: vi.fn(async () => []) });
    render(<SchedulesPanel api={api} teamId={1} teamName="Morning desk" tools={[]} onClose={vi.fn()} onWatchRun={vi.fn()} />);

    await userEvent.click(await screen.findByRole("button", { name: "New schedule" }));
    const cron = screen.getByLabelText("Cron");
    await userEvent.clear(cron);
    await userEvent.type(cron, "0 9 * * MON-FRI");
    await userEvent.click(screen.getByRole("button", { name: "Create schedule" }));

    await waitFor(() =>
      expect(api.createSchedule).toHaveBeenCalledWith(
        1,
        expect.objectContaining({ cronExpression: "0 9 * * MON-FRI", revisionMode: "pinned" }),
        expect.anything(),
      ),
    );
    // The list is asked again rather than the panel guessing what changed.
    expect((api.listSchedules as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(1);
  });

  it("shows the module's own refusal, unchanged", async () => {
    const api = fakeApi({
      createSchedule: vi.fn(async () => {
        throw new MarketDataError("refused", "not a valid five-field cron expression");
      }),
    });
    render(<SchedulesPanel api={api} teamId={1} teamName="Morning desk" tools={[]} onClose={vi.fn()} onWatchRun={vi.fn()} />);

    await userEvent.click(await screen.findByRole("button", { name: "New schedule" }));
    await userEvent.click(screen.getByRole("button", { name: "Create schedule" }));

    expect(await screen.findByText("not a valid five-field cron expression")).toBeInTheDocument();
  });

  it("toggles enabled through the module and shows a disabled reason it wrote", async () => {
    const disabled = {
      ...SCHEDULE,
      enabled: false,
      disabledReason: "3 kolejne przebiegi zakończone niepowodzeniem",
    };
    let disabledYet = false;
    const api = fakeApi({
      // The row's own state comes from the reload `onChanged` triggers, exactly as it
      // would against the real module — not from the disable call's own response.
      listSchedules: vi.fn(async () => [disabledYet ? disabled : SCHEDULE]),
      disableSchedule: vi.fn(async () => {
        disabledYet = true;
        return disabled;
      }),
    });
    render(<SchedulesPanel api={api} teamId={1} teamName="Morning desk" tools={[]} onClose={vi.fn()} onWatchRun={vi.fn()} />);

    await userEvent.click(within(await scheduleRow()).getByRole("button", { name: "Disable" }));

    expect(api.disableSchedule).toHaveBeenCalledWith(SCHEDULE.id, expect.anything());
    expect(await screen.findByText(/3 kolejne przebiegi zakończone niepowodzeniem/)).toBeInTheDocument();
  });
});

describe("fire history", () => {
  const SKIPPED: ScheduleFire = {
    id: 1,
    scheduleId: SCHEDULE.id,
    triggerId: null,
    firedAt: 1_755_374_400,
    outcome: "skipped",
    reason: "the previous run of this schedule is still working",
    runId: null,
    skippedCount: 0,
  };
  const STARTED: ScheduleFire = {
    id: 2,
    scheduleId: SCHEDULE.id,
    triggerId: null,
    firedAt: 1_755_374_700,
    outcome: "started",
    reason: null,
    runId: 42,
    skippedCount: 3,
  };

  it("shows a fire that started nothing, with its reason and no way to watch it", async () => {
    const api = fakeApi({ scheduleFires: vi.fn(async () => [SKIPPED]) });
    render(<SchedulesPanel api={api} teamId={1} teamName="Morning desk" tools={[]} onClose={vi.fn()} onWatchRun={vi.fn()} />);

    await userEvent.click(within(await scheduleRow()).getByRole("button", { name: "History" }));

    const entry = await screen.findByText(/still working/);
    expect(within(entry.closest("li")!).queryByRole("button", { name: "Watch" })).not.toBeInTheDocument();
  });

  it("leads to the run's own trace for a fire that started one, folded slots and all", async () => {
    const onWatchRun = vi.fn();
    const api = fakeApi({ scheduleFires: vi.fn(async () => [STARTED]) });
    render(<SchedulesPanel api={api} teamId={1} teamName="Morning desk" tools={[]} onClose={vi.fn()} onWatchRun={onWatchRun} />);

    await userEvent.click(within(await scheduleRow()).getByRole("button", { name: "History" }));
    expect(await screen.findByText(/3 folded in/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Watch" }));

    expect(onWatchRun).toHaveBeenCalledWith(42);
  });
});

describe("triggers", () => {
  it("shows an unknown last read as a third state, not as false", async () => {
    const api = fakeApi();
    render(<SchedulesPanel api={api} teamId={1} teamName="Morning desk" tools={[]} onClose={vi.fn()} onWatchRun={vi.fn()} />);

    expect(await screen.findByText(/unknown — the tool server could not be asked/)).toBeInTheDocument();
  });

  it("posts a new trigger naming a tool the module announces, with its JSON arguments", async () => {
    const api = fakeApi({ listTriggers: vi.fn(async () => []) });
    render(
      <SchedulesPanel
        api={api}
        teamId={1}
        teamName="Morning desk"
        tools={[{ name: "read_indicators", description: "reads indicators", readOnly: true }]}
        onClose={vi.fn()}
        onWatchRun={vi.fn()}
      />,
    );

    await userEvent.click(await screen.findByRole("button", { name: "New trigger" }));
    await userEvent.selectOptions(screen.getByLabelText("Tool"), "read_indicators");
    await userEvent.type(screen.getByLabelText("Field"), "rsi");
    await userEvent.type(screen.getByLabelText("Threshold"), "70");
    await userEvent.click(screen.getByRole("button", { name: "Create trigger" }));

    await waitFor(() =>
      expect(api.createTrigger).toHaveBeenCalledWith(
        1,
        expect.objectContaining({ toolName: "read_indicators", fieldPath: "rsi", threshold: "70" }),
        expect.anything(),
      ),
    );
  });

  it("refuses to submit while the arguments are not valid JSON", async () => {
    const api = fakeApi();
    render(<SchedulesPanel api={api} teamId={1} teamName="Morning desk" tools={[]} onClose={vi.fn()} onWatchRun={vi.fn()} />);

    await userEvent.click(await screen.findByRole("button", { name: "New trigger" }));
    const args = screen.getByLabelText(/Arguments/);
    fireEvent.change(args, { target: { value: "{not json" } });

    expect(screen.getByRole("button", { name: "Create trigger" })).toBeDisabled();
  });
});
