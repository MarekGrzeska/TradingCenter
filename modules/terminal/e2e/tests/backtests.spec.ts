import { expect, test, type Page } from "@playwright/test";
import { createStrategy, daysAgo, finishedRun, openStrategy, strategyDocument, uniqueName } from "../support";

/** Runs, reports and comparisons against a live workbench (`docs/strategie-scenariusze-testowe.html`, sections 05–07). */

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
