import { expect, test, type Page } from "@playwright/test";
import { createStrategy, daysAgo, finishedRun, openStrategy, queuedRun, strategyDocument, uniqueName } from "../support";

/** Runs, reports and comparisons against a live workbench (`docs/strategie/strategie-scenariusze-testowe.html`, sections 05–07). */

const runs = (page: Page) => page.getByRole("table", { name: "Uruchomienia" });
const runRow = (page: Page, id: number) => runs(page).getByRole("row").filter({ has: page.getByRole("cell", { name: String(id), exact: true }) });

test("BT-01 goes from a strategy to its backtests with the run form", async ({ page, request }) => {
  const name = uniqueName("BT-01");
  const id = await createStrategy(request, strategyDocument(name));
  await openStrategy(page, name);

  await page.getByRole("link", { name: "Backtesty tej strategii →" }).click();

  await expect(page).toHaveURL(new RegExp(`/backtests\\?strategy=${id}`));
  await expect(page.getByRole("form", { name: "Uruchomienie" })).toContainText("Backtest rewizji 1");
});

test("BT-02 runs a backtest from the form and sees it finish without a reload", async ({ page, request }) => {
  const id = await createStrategy(request, strategyDocument(uniqueName("BT-02")));
  await page.goto(`/backtests?strategy=${id}`);
  const form = page.getByRole("form", { name: "Uruchomienie" });
  await expect(form).toContainText("z profilu wpisanego przez operatora");

  await form.getByLabel("Od (dzień, czas polski)").fill(daysAgo(20));
  await form.getByLabel("Do (bez tego dnia)").fill(daysAgo(2));
  await form.getByRole("button", { name: "Uruchom backtest" }).click();

  await expect(runs(page).getByRole("row").nth(1)).toContainText("gotowe", { timeout: 30_000 });
});

test("BT-03 says a range over the ceiling before anything is sent", async ({ page, request }) => {
  const id = await createStrategy(request, strategyDocument(uniqueName("BT-03")));
  await page.goto(`/backtests?strategy=${id}`);
  const form = page.getByRole("form", { name: "Uruchomienie" });

  await form.getByLabel("Od (dzień, czas polski)").fill("2020-01-01");

  await expect(form).toContainText("skróć zakres");
  await expect(form.getByRole("button", { name: "Uruchom backtest" })).toBeDisabled();
});

test("BT-04 marks a run without costs in the list and in its report", async ({ page, request }) => {
  const id = await createStrategy(request, strategyDocument(uniqueName("BT-04")));
  const run = await finishedRun(request, id, { withoutCosts: true });
  await page.goto(`/backtests?strategy=${id}`);

  await expect(runRow(page, run)).toContainText("bez kosztów");
  await runRow(page, run).click();
  await expect(page.getByRole("note")).toContainText("bez kosztów — wynik pomija spread, poślizg i finansowanie");
});

test("BT-05 reads a report: metrics, the source of costs and the trades", async ({ page, request }) => {
  const id = await createStrategy(request, strategyDocument(uniqueName("BT-05")));
  const run = await finishedRun(request, id);
  await page.goto(`/backtests?strategy=${id}`);

  await runRow(page, run).click();

  await expect(page.getByText("koszty z profilu operatora")).toBeVisible();
  const trades = page.getByRole("table", { name: "Transakcje" });
  await expect(trades.getByRole("row").nth(1)).toBeVisible();
  await trades.getByRole("row").nth(1).click();
  await expect(page.getByText(/Transakcje 1–\d+ z \d+/)).toBeVisible();
});

test("BT-06 says a run with no trades had none, with dashes instead of zeros", async ({ page, request }) => {
  const id = await createStrategy(request, strategyDocument(uniqueName("BT-06"), { entries: [{ side: "long", when: "close < 0" }] }));
  const run = await finishedRun(request, id);
  await page.goto(`/backtests?strategy=${id}`);

  await runRow(page, run).click();

  await expect(page.getByText("W tym zakresie strategia nie otworzyła żadnej pozycji.")).toBeVisible();
  await expect(page.getByRole("definition").filter({ hasText: "—" }).first()).toBeVisible();
});

test("BT-07 compares two runs side by side, a column each", async ({ page, request }) => {
  const id = await createStrategy(request, strategyDocument(uniqueName("BT-07")));
  const a = await finishedRun(request, id, { params: { stop: 40 } });
  const b = await finishedRun(request, id, { params: { stop: 60 } });
  await page.goto(`/backtests?strategy=${id}`);

  await page.getByRole("checkbox", { name: `Porównaj uruchomienie ${a}` }).check();
  await page.getByRole("checkbox", { name: `Porównaj uruchomienie ${b}` }).check();
  await page.getByRole("button", { name: "Porównaj (2)" }).click();

  const table = page.getByRole("table", { name: "Porównanie" });
  await expect(table.getByRole("columnheader", { name: new RegExp(`#${a} `) })).toContainText("stop=40");
  await expect(table.getByRole("columnheader", { name: new RegExp(`#${b} `) })).toContainText("stop=60");
});

test("BT-08 refuses runs of different ranges and says why", async ({ page, request }) => {
  const id = await createStrategy(request, strategyDocument(uniqueName("BT-08")));
  const a = await finishedRun(request, id, { from: 20 });
  const b = await finishedRun(request, id, { from: 10 });
  await page.goto(`/backtests?strategy=${id}`);

  await page.getByRole("checkbox", { name: `Porównaj uruchomienie ${a}` }).check();
  await expect(page.getByRole("button", { name: "Porównaj (1)" })).toBeDisabled();
  await page.getByRole("checkbox", { name: `Porównaj uruchomienie ${b}` }).check();
  await page.getByRole("button", { name: "Porównaj (2)" }).click();

  await expect(page.getByRole("alert")).toContainText(`run ${b} covers`);
  await expect(page.getByRole("table", { name: "Porównanie" })).toHaveCount(0);
});

test("BT-09 sends nothing to the queue for a parameter outside its declared range", async ({ page, request }) => {
  const id = await createStrategy(request, strategyDocument(uniqueName("BT-09")));
  await page.goto(`/backtests?strategy=${id}`);
  const form = page.getByRole("form", { name: "Uruchomienie" });
  await expect(form).toContainText("z profilu wpisanego przez operatora");

  await form.getByLabel(/p\.stop/).fill("500");
  await form.getByRole("button", { name: "Uruchom backtest" }).click();

  await expect(page.getByText("Ta strategia nie miała jeszcze uruchomień.")).toBeVisible();
});

test("BT-10 cancels a run that waits in the queue", async ({ page, request }) => {
  const id = await createStrategy(request, strategyDocument(uniqueName("BT-10")));
  await queuedRun(request, id, { from: 28 });
  const waiting = await queuedRun(request, id, { from: 28 });
  await page.goto(`/backtests?strategy=${id}`);

  await runRow(page, waiting).getByRole("button", { name: "Anuluj" }).click();

  await expect(runRow(page, waiting)).toContainText("anulowane");
  await expect(runRow(page, waiting).getByRole("button", { name: "Anuluj" })).toHaveCount(0);
});

test("BT-11 names a close on a moved stop a trailing stop, not a stop", async ({ page, request }) => {
  const trailing = strategyDocument(uniqueName("BT-11"), {
    exits: { stop: "entry_price - p.stop", trail: { after_r: 0.3, distance: "0.3 * p.stop" }, max_bars: 48 },
  });
  const id = await createStrategy(request, trailing);
  const run = await finishedRun(request, id);
  await page.goto(`/backtests?strategy=${id}`);

  await runRow(page, run).click();

  const trades = page.getByRole("table", { name: "Transakcje" });
  await expect(trades.getByRole("cell", { name: "stop kroczący" }).first()).toBeVisible();
});

test("BT-12 lists runs of every strategy with their names and compares across strategies", async ({ page, request }) => {
  const nameA = uniqueName("BT-12a");
  const nameB = uniqueName("BT-12b");
  const a = await finishedRun(request, await createStrategy(request, strategyDocument(nameA)));
  const b = await finishedRun(request, await createStrategy(request, strategyDocument(nameB)));
  await page.goto("/backtests");

  // Across strategies another run's trade count can equal an id, so the row is found by its id column alone.
  const rowOf = (run: number) => runs(page).getByRole("row").filter({ has: page.locator("td:nth-child(2)", { hasText: new RegExp(`^${run}$`) }) });
  await expect(rowOf(a)).toContainText(nameA);
  await expect(rowOf(b)).toContainText(nameB);
  const ids = await runs(page).getByRole("row").locator("td:nth-child(2)").allTextContents();
  expect(ids.indexOf(String(b))).toBeLessThan(ids.indexOf(String(a)));

  await page.getByRole("checkbox", { name: `Porównaj uruchomienie ${a}` }).check();
  await page.getByRole("checkbox", { name: `Porównaj uruchomienie ${b}` }).check();
  await page.getByRole("button", { name: "Porównaj (2)" }).click();

  const table = page.getByRole("table", { name: "Porównanie" });
  await expect(table.getByRole("columnheader", { name: new RegExp(`#${a} `) })).toBeVisible();
  await expect(table.getByRole("columnheader", { name: new RegExp(`#${b} `) })).toBeVisible();
});

test("BT-13 ticks only finished runs and compares between two and five", async ({ page, request }) => {
  const id = await createStrategy(request, strategyDocument(uniqueName("BT-13")));
  const done: number[] = [];
  for (let i = 0; i < 6; i++) done.push(await finishedRun(request, id, { from: 6, to: 2, params: { stop: 20 + 10 * i } }));
  await queuedRun(request, id, { from: 28 });
  await queuedRun(request, id, { from: 28 });
  const waiting = await queuedRun(request, id, { from: 28 });
  await page.goto(`/backtests?strategy=${id}`);

  await expect(page.getByRole("checkbox", { name: `Porównaj uruchomienie ${waiting}` })).toBeDisabled();
  for (const run of done.slice(0, 5)) await page.getByRole("checkbox", { name: `Porównaj uruchomienie ${run}` }).check();
  await expect(page.getByRole("button", { name: "Porównaj (5)" })).toBeEnabled();
  await page.getByRole("checkbox", { name: `Porównaj uruchomienie ${done[5]}` }).check();
  await expect(page.getByRole("button", { name: "Porównaj (6)" })).toBeDisabled();
});
