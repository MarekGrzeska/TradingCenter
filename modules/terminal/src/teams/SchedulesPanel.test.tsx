import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { agentActivity } from "../agent/agentActivity";
import { MarketDataError } from "../data/types";
import { formatInstant } from "../ui/formatTime";
import { SchedulesPanel } from "./SchedulesPanel";
import type { Schedule, ScheduleFire, TeamRevision, TeamsApi, Trigger } from "./teamsApi";

/** Where the operator's browser is, which the panel reads once per render and a test
 *  cannot set by moving the machine. The zone the schedule itself is written in is not in
 *  question — that one is Poland's, always. */
const zone = vi.hoisted(() => ({ outsidePoland: false }));

vi.mock("../ui/formatTime", async () => {
  const actual = await vi.importActual<typeof import("../ui/formatTime")>("../ui/formatTime");
  return {
    ...actual,
    browserIsInScheduleZone: () => !zone.outsidePoland,
    formatBrowserInstant: (epochSeconds: number) =>
      `${actual.formatInstant(epochSeconds)} in the operator's own zone`,
  };
});

beforeEach(() => {
  zone.outsidePoland = false;
});

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
  recurrence: { kind: "every_minutes", minutes: 5, minute: null, hour: null, weekdays: null, dayOfMonth: null },
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
  const rhythm = await screen.findByText(/Every 5 minutes/);
  const li = rhythm.closest("li");
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
    previewNextFires: vi.fn(async () => []),
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
  it("shows the module's own timestamp in Polish time — never recomputed", async () => {
    const api = fakeApi();
    render(<SchedulesPanel api={api} teamId={1} teamName="Morning desk" tools={[]} onClose={vi.fn()} onWatchRun={vi.fn()} />);

    // The exact instant the module answered with — nothing here parses `*/5 * * * *`
    // to produce it.
    expect(await screen.findByText(new RegExp(formatInstant(SCHEDULE.nextFireAt)))).toBeInTheDocument();
  });

  it("previews a draft's next fires from the module, not from a local parser", async () => {
    // Deliberately not slots any rhythm in the form would land on, so a passing test
    // proves the value came from `previewNextFires` and not from a parser here.
    const oddTimes = [1_755_000_037, 1_755_000_911];
    const api = fakeApi({ previewNextFires: vi.fn(async () => oddTimes) });
    render(<SchedulesPanel api={api} teamId={1} teamName="Morning desk" tools={[]} onClose={vi.fn()} onWatchRun={vi.fn()} />);

    await userEvent.click(within(await scheduleRow()).getByRole("button", { name: "Edit" }));

    await waitFor(() =>
      expect(api.previewNextFires).toHaveBeenCalledWith(
        expect.objectContaining({ recurrence: expect.objectContaining({ kind: "every_minutes" }) }),
        3,
        expect.anything(),
      ),
    );
    for (const t of oddTimes) {
      expect(await screen.findByText(new RegExp(formatInstant(t)))).toBeInTheDocument();
    }
  });

  it("asks the module again when the operator changes the time, before anything is saved", async () => {
    const api = fakeApi({ listSchedules: vi.fn(async () => []) });
    render(<SchedulesPanel api={api} teamId={1} teamName="Morning desk" tools={[]} onClose={vi.fn()} onWatchRun={vi.fn()} />);

    await userEvent.click(await screen.findByRole("button", { name: "New schedule" }));
    fireEvent.change(screen.getByLabelText("Time of day"), { target: { value: "06:45" } });

    await waitFor(() =>
      expect(api.previewNextFires).toHaveBeenCalledWith(
        expect.objectContaining({ recurrence: expect.objectContaining({ hour: 6, minute: 45 }) }),
        3,
        expect.anything(),
      ),
    );
    expect(api.createSchedule).not.toHaveBeenCalled();
  });

  it("shows the browser's own zone beside Polish time for an operator outside Poland", async () => {
    zone.outsidePoland = true;
    const api = fakeApi({ previewNextFires: vi.fn(async () => [SCHEDULE.nextFireAt]) });
    render(<SchedulesPanel api={api} teamId={1} teamName="Morning desk" tools={[]} onClose={vi.fn()} onWatchRun={vi.fn()} />);

    await userEvent.click(within(await scheduleRow()).getByRole("button", { name: "Edit" }));

    // Both readings of the same second: the zone the schedule is written in, and the one
    // the operator is sitting in.
    expect(await screen.findByText(/in the operator's own zone/)).toBeInTheDocument();
  });
});

describe("what the chat changed", () => {
  it("re-reads after an agent turn, because schedule_team is a chat tool too", async () => {
    // The same staleness the catalogue had: `schedule_team` and `trigger_team` write in
    // the module and nothing about them reaches this panel (`agentActivity.ts`).
    const listSchedules = vi
      .fn()
      .mockResolvedValueOnce([])
      .mockResolvedValue([{ ...SCHEDULE, cronExpression: "30 8 * * 1-5", recurrence: null }]);
    render(
      <SchedulesPanel
        api={fakeApi({ listSchedules })}
        teamId={1}
        teamName="Morning desk"
        tools={[]}
        onClose={vi.fn()}
        onWatchRun={vi.fn()}
      />,
    );
    await waitFor(() => expect(listSchedules).toHaveBeenCalledTimes(1));

    agentActivity.turnFinished();

    expect(await screen.findByText(/30 8 \* \* 1-5/)).toBeInTheDocument();
  });
});

describe("creating and editing a schedule", () => {
  it("posts a rhythm the operator chose, with no cron expression typed anywhere", async () => {
    const api = fakeApi({ listSchedules: vi.fn(async () => []) });
    render(<SchedulesPanel api={api} teamId={1} teamName="Morning desk" tools={[]} onClose={vi.fn()} onWatchRun={vi.fn()} />);

    await userEvent.click(await screen.findByRole("button", { name: "New schedule" }));
    await userEvent.click(screen.getByText("On chosen weekdays"));
    fireEvent.change(screen.getByLabelText("Time of day"), { target: { value: "08:30" } });
    await userEvent.click(screen.getByRole("button", { name: "Sat" }));
    await userEvent.click(screen.getByRole("button", { name: "Create schedule" }));

    await waitFor(() =>
      expect(api.createSchedule).toHaveBeenCalledWith(
        1,
        expect.objectContaining({
          revisionMode: "pinned",
          cronExpression: null,
          recurrence: expect.objectContaining({
            kind: "weekly",
            hour: 8,
            minute: 30,
            weekdays: [1, 2, 3, 4, 5, 6],
          }),
        }),
        expect.anything(),
      ),
    );
    // The list is asked again rather than the panel guessing what changed.
    expect((api.listSchedules as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(1);
  });

  it("turns the weekend off on an hourly rhythm, without a cron expression", async () => {
    const api = fakeApi({ listSchedules: vi.fn(async () => []) });
    render(<SchedulesPanel api={api} teamId={1} teamName="Morning desk" tools={[]} onClose={vi.fn()} onWatchRun={vi.fn()} />);

    await userEvent.click(await screen.findByRole("button", { name: "New schedule" }));
    await userEvent.click(screen.getByText("Every hour"));
    fireEvent.change(screen.getByLabelText("Minute of the hour"), { target: { value: "35" } });
    await userEvent.click(screen.getByRole("button", { name: "Sat" }));
    await userEvent.click(screen.getByRole("button", { name: "Sun" }));
    await userEvent.click(screen.getByRole("button", { name: "Create schedule" }));

    await waitFor(() =>
      expect(api.createSchedule).toHaveBeenCalledWith(
        1,
        expect.objectContaining({
          cronExpression: null,
          recurrence: expect.objectContaining({
            kind: "hourly",
            minute: 35,
            weekdays: [1, 2, 3, 4, 5],
          }),
        }),
        expect.anything(),
      ),
    );
  });

  it("sends every day as no days at all, so one trigger has one shape", async () => {
    const api = fakeApi({ listSchedules: vi.fn(async () => []) });
    render(<SchedulesPanel api={api} teamId={1} teamName="Morning desk" tools={[]} onClose={vi.fn()} onWatchRun={vi.fn()} />);

    await userEvent.click(await screen.findByRole("button", { name: "New schedule" }));
    await userEvent.click(screen.getByText("Every hour"));
    // Off and straight back on: the form must end where it started, not on seven days.
    await userEvent.click(screen.getByRole("button", { name: "Sat" }));
    await userEvent.click(screen.getByRole("button", { name: "Sat" }));
    await userEvent.click(screen.getByRole("button", { name: "Create schedule" }));

    await waitFor(() =>
      expect(api.createSchedule).toHaveBeenCalledWith(
        1,
        expect.objectContaining({
          recurrence: expect.objectContaining({ kind: "hourly", weekdays: null }),
        }),
        expect.anything(),
      ),
    );
  });

  it("offers no days at all under the daily rhythm", async () => {
    // Daily on chosen days is `weekly`, and the module refuses the second spelling — so the
    // wizard must not be able to build it.
    const api = fakeApi({ listSchedules: vi.fn(async () => []) });
    render(<SchedulesPanel api={api} teamId={1} teamName="Morning desk" tools={[]} onClose={vi.fn()} onWatchRun={vi.fn()} />);

    await userEvent.click(await screen.findByRole("button", { name: "New schedule" }));
    await userEvent.click(screen.getByText("Every day"));

    expect(screen.queryByRole("button", { name: "Sat" })).not.toBeInTheDocument();
    expect(screen.queryByText("On which days?")).not.toBeInTheDocument();
  });

  it("keeps the last day rather than letting a schedule fire on none", async () => {
    const api = fakeApi({ listSchedules: vi.fn(async () => []) });
    render(<SchedulesPanel api={api} teamId={1} teamName="Morning desk" tools={[]} onClose={vi.fn()} onWatchRun={vi.fn()} />);

    await userEvent.click(await screen.findByRole("button", { name: "New schedule" }));
    await userEvent.click(screen.getByText("Every hour"));
    for (const day of ["Tue", "Wed", "Thu", "Fri", "Sat", "Sun", "Mon"]) {
      await userEvent.click(screen.getByRole("button", { name: day }));
    }

    expect(screen.getByRole("button", { name: "Mon" })).toHaveAttribute("aria-pressed", "true");
  });

  it("opens a schedule the wizard has no rhythm for on its own expression, and saves it unchanged", async () => {
    const written = { ...SCHEDULE, cronExpression: "0 9 * * MON-FRI", recurrence: null };
    const api = fakeApi({ listSchedules: vi.fn(async () => [written]) });
    render(<SchedulesPanel api={api} teamId={1} teamName="Morning desk" tools={[]} onClose={vi.fn()} onWatchRun={vi.fn()} />);

    const row = (await screen.findByText("0 9 * * MON-FRI")).closest("li")!;
    await userEvent.click(within(row).getByRole("button", { name: "Edit" }));
    await userEvent.click(screen.getByRole("button", { name: "Save schedule" }));

    await waitFor(() =>
      expect(api.updateSchedule).toHaveBeenCalledWith(
        written.id,
        expect.objectContaining({ cronExpression: "0 9 * * MON-FRI", recurrence: null }),
        expect.anything(),
      ),
    );
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

  it("shows the module's own words when enabling is refused", async () => {
    // Without this the rejected call was invisible: the button went back to saying
    // "Enable" and the operator was left with a schedule that had not changed and no
    // reason why (`terminal-teams-schedules`, "Odmowa modułu jest pokazana słowami
    // modułu").
    const api = fakeApi({
      listSchedules: vi.fn(async () => [{ ...SCHEDULE, enabled: false, disabledReason: null }]),
      enableSchedule: vi.fn(async () => {
        throw new MarketDataError("refused", "agent 'trader' carries tool(s) ['place_order']");
      }),
    });
    render(<SchedulesPanel api={api} teamId={1} teamName="Morning desk" tools={[]} onClose={vi.fn()} onWatchRun={vi.fn()} />);

    await userEvent.click(within(await scheduleRow()).getByRole("button", { name: "Enable" }));

    expect(await screen.findByText(/place_order/)).toBeInTheDocument();
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
