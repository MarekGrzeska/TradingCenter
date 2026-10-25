import { expect, type APIRequestContext, type Page } from "@playwright/test";

/**
 * Setting up through REST, the way the terminal's own client calls it (through Vite's proxy): what a test clicks is what
 * it checks, and nothing else. The stack holds `seed.py`'s thirty weekdays of US100 minutes up to today's UTC midnight.
 */

export type StrategyDocument = Record<string, unknown>;

export function uniqueName(label: string): string {
  return `${label} ${Date.now().toString(36)}`;
}

export function strategyDocument(name: string, changes: StrategyDocument = {}): StrategyDocument {
  return {
    schema: 1,
    name,
    symbol: "US100",
    timeframe: "HOUR",
    params: { stop: { default: 50, min: 20, max: 100, step: 10 } },
    entries: [{ side: "long", when: "hour == 9" }],
    exits: { stop: "entry_price - p.stop", target: "entry_price + p.stop" },
    sizing: { mode: "fixed_units", value: 1 },
    ...changes,
  };
}

export async function createStrategy(request: APIRequestContext, document: StrategyDocument): Promise<number> {
  const response = await request.post("/strategies-api/strategies", { data: document });
  expect(response.status(), await response.text()).toBe(201);
  return (await response.json()).strategy_id;
}

export async function saveRevision(
  request: APIRequestContext,
  strategyId: number,
  document: StrategyDocument,
  basedOn: number,
): Promise<number> {
  const response = await request.post(`/strategies-api/strategies/${strategyId}/revisions?based_on=${basedOn}`, {
    data: document,
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  return (await response.json()).revision;
}

/** A UTC midnight `days` before today's, as the run request and the date inputs spell it. */
export function daysAgo(days: number): string {
  const at = new Date();
  at.setUTCHours(0, 0, 0, 0);
  at.setUTCDate(at.getUTCDate() - days);
  return at.toISOString().slice(0, 10);
}

export interface RunOptions {
  from?: number;
  to?: number;
  params?: Record<string, number>;
  withoutCosts?: boolean;
}

/** Queues a run and returns at once; the instrument's cost profile is the one `seed.py` set. */
export async function queuedRun(request: APIRequestContext, strategyId: number, options: RunOptions = {}): Promise<number> {
  const body = {
    strategy_id: strategyId,
    from: `${daysAgo(options.from ?? 20)}T00:00:00Z`,
    to: `${daysAgo(options.to ?? 2)}T00:00:00Z`,
    params: options.params ?? {},
    ...(options.withoutCosts ? { without_costs: true } : {}),
  };
  const queued = await request.post("/strategies-api/runs", { data: body });
  expect(queued.status(), await queued.text()).toBe(202);
  return (await queued.json()).id;
}

/** Queues a run and waits for it to end. */
export async function finishedRun(request: APIRequestContext, strategyId: number, options: RunOptions = {}): Promise<number> {
  const id = await queuedRun(request, strategyId, options);
  await expect
    .poll(async () => (await (await request.get(`/strategies-api/runs/${id}`)).json()).status, { timeout: 30_000 })
    .toBe("done");
  return id;
}

export async function openStrategy(page: Page, name: string): Promise<void> {
  await page.goto("/strategies");
  await page.getByRole("complementary", { name: "Strategie" }).getByRole("button", { name: new RegExp(name) }).click();
  await expect(page.getByRole("heading", { name: new RegExp(`${name} · rewizja`) })).toBeVisible();
}

/** CodeMirror is a contenteditable, which `fill()` does not drive: select everything and type over it. */
export async function replaceEditorText(page: Page, text: string): Promise<void> {
  const editor = page.locator(".cm-content");
  await editor.click();
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.insertText(text);
}

export function documentText(document: StrategyDocument): string {
  return JSON.stringify(document, null, 2);
}
