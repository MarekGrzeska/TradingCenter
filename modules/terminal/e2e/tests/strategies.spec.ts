import { expect, test } from "@playwright/test";
import {
  createStrategy,
  documentText,
  openStrategy,
  replaceEditorText,
  saveRevision,
  strategyDocument,
  uniqueName,
} from "../support";

/** The Strategies tab against a live workbench (`docs/strategie/strategie-scenariusze-testowe.html`, sections 01–03). */

const ATR_STOP = (multiple: number) => ({
  params: {},
  exits: { stop: `entry_price - ${multiple} * at_entry(atr(14))`, target: `entry_price + ${multiple} * at_entry(atr(14))` },
});

test("ST-01 opens a strategy from the list with its editor, chat and summary", async ({ page, request }) => {
  const name = uniqueName("ST-01");
  await createStrategy(request, strategyDocument(name));

  await openStrategy(page, name);

  await expect(page.getByRole("complementary", { name: "Czat strategii" })).toBeVisible();
  await expect(page.getByRole("complementary", { name: "Streszczenie" })).toContainText(name);
  await expect(page.locator(".cm-content")).toContainText(name);
  await expect(page.getByRole("list", { name: "Rewizje" })).toContainText("rewizja 1");
});

test("ST-02 marks an unknown function in its formula and will not save", async ({ page, request }) => {
  const name = uniqueName("ST-02");
  await createStrategy(request, strategyDocument(name));
  await openStrategy(page, name);

  await replaceEditorText(page, documentText(strategyDocument(name, { entries: [{ side: "long", when: "emaa(20) > close" }] })));

  await expect(page.getByRole("complementary", { name: "Streszczenie" })).toContainText("Dokument ma problemy");
  await expect(page.locator(".cm-lintRange-error").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Zapisz", exact: true })).toBeDisabled();
});

test("ST-03 saves an edit as the next revision and the summary follows it", async ({ page, request }) => {
  const name = uniqueName("ST-03");
  await createStrategy(request, strategyDocument(name, ATR_STOP(2)));
  await openStrategy(page, name);

  await replaceEditorText(page, documentText(strategyDocument(name, ATR_STOP(1.5))));
  await expect(page.getByRole("complementary", { name: "Streszczenie" })).toContainText("1,5 × ATR(14)");
  await page.getByRole("button", { name: "Zapisz", exact: true }).click();

  await expect(page.getByText("Zapisano rewizję 2.")).toBeVisible();
  await expect(page.getByRole("heading", { name: new RegExp(`${name} · rewizja 2 \\(operator\\)`) })).toBeVisible();
  // Nothing to save until the text differs from the revision again.
  await expect(page.getByRole("button", { name: "Zapisz", exact: true })).toBeDisabled();
});

test("ST-04 keeps the operator's edit when someone else saved first", async ({ page, request }) => {
  const name = uniqueName("ST-04");
  const id = await createStrategy(request, strategyDocument(name));
  await openStrategy(page, name);

  await saveRevision(request, id, strategyDocument(name, { params: { stop: { default: 60, min: 20, max: 100, step: 10 } } }), 1);
  const mine = strategyDocument(name, { entries: [{ side: "long", when: "hour == 10" }] });
  await replaceEditorText(page, documentText(mine));
  await page.getByRole("button", { name: "Zapisz", exact: true }).click();

  await expect(page.getByRole("status")).toContainText("Istnieje nowsza rewizja 2");
  await expect(page.locator(".cm-content")).toContainText("hour == 10");
  await expect(page.getByRole("heading", { name: new RegExp(`${name} · rewizja 1`) })).toBeVisible();
});

test("ST-05 shows what a revision changed and restores an older one as a new revision", async ({ page, request }) => {
  const name = uniqueName("ST-05");
  const id = await createStrategy(request, strategyDocument(name, ATR_STOP(2)));
  await saveRevision(request, id, strategyDocument(name, ATR_STOP(1.5)), 1);
  await openStrategy(page, name);

  const revisions = page.getByRole("list", { name: "Rewizje" });
  await revisions.getByRole("button", { name: /rewizja 2/ }).click();
  await expect(page.getByRole("cell", { name: "exits.stop" })).toBeVisible();

  await revisions.getByRole("button", { name: /rewizja 1/ }).click();
  await page.getByRole("button", { name: "Przywróć jako nową rewizję" }).click();

  await expect(page.getByText("Rewizja 1 przywrócona jako rewizja 3.")).toBeVisible();
  await expect(page.locator(".cm-content")).toContainText("2 * at_entry(atr(14))");
});

test("ST-06 archives a strategy out of the list and restores it", async ({ page, request }) => {
  const name = uniqueName("ST-06");
  await createStrategy(request, strategyDocument(name));
  await openStrategy(page, name);
  const list = page.getByRole("complementary", { name: "Strategie" });

  await page.getByRole("button", { name: "Archiwizuj" }).click();
  await expect(list.getByRole("button", { name: new RegExp(name) })).toHaveCount(0);

  await list.getByRole("checkbox", { name: "zarchiwizowane" }).check();
  await list.getByRole("button", { name: new RegExp(name) }).click();
  await page.getByRole("button", { name: "Przywróć", exact: true }).click();
  await list.getByRole("checkbox", { name: "zarchiwizowane" }).uncheck();

  await expect(list.getByRole("button", { name: new RegExp(name) })).toBeVisible();
});

test("ST-07 summarises a multi-timeframe condition and a no-entry limit in words", async ({ page, request }) => {
  const name = uniqueName("ST-07");
  await createStrategy(request, strategyDocument(name));
  await openStrategy(page, name);

  await replaceEditorText(
    page,
    documentText(
      strategyDocument(name, {
        entries: [{ side: "long", when: "ema(20) @ HOUR_4 > ema(50) @ HOUR_4" }],
        limits: { no_entry: "weekday == FRIDAY and hour >= 18" },
      }),
    ),
  );

  const summary = page.getByRole("complementary", { name: "Streszczenie" });
  await expect(summary).toContainText("EMA(20) na h4 powyżej EMA(50) na h4");
  await expect(summary).toContainText("od 18:00 UTC, czyli 19:00 zimą i 20:00 latem w Polsce");
});
