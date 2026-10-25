import { expect, test, type Page } from "@playwright/test";
import { uniqueName } from "../support";

/**
 * The Alerts tab against a live workbench with its package mounted: the one recipient `seed.py` made, and no clock that
 * looks at anything (`SCHEDULER_ENABLED=false` is the workbench's; the alerts clock only checks rules, and these never fire).
 */

const RECIPIENT = "e2e-operator";

const rule = (page: Page, name: string) => page.getByRole("listitem").filter({ hasText: name });
const dialog = (page: Page) => page.getByRole("dialog");

async function startEventRule(page: Page, name: string): Promise<void> {
  await page.goto("/alerts");
  await page.getByRole("button", { name: "Nowa reguła…" }).click();
  await dialog(page).getByLabel("Nazwa").fill(name);
  await dialog(page).getByRole("radio", { name: /Coś się wydarzy/ }).check();
  await dialog(page).getByLabel("Zdarzenie").selectOption("teams.run.finished");
  await dialog(page).getByLabel("Kogo powiadomić").selectOption(RECIPIENT);
}

test("AL-01 a rule made in the form is listed with whom it tells, and is still there after a reload", async ({ page }) => {
  const name = uniqueName("AL-01");
  await startEventRule(page, name);

  await dialog(page).getByRole("button", { name: "Zapisz" }).click();

  await expect(rule(page, name)).toContainText(`→ ${RECIPIENT} przez @e2e_bot`);
  await expect(rule(page, name)).toContainText("działa");
  await page.reload();
  await expect(rule(page, name)).toBeVisible();
});

test("AL-02 a rule is switched off, shown as off, and removed after a confirmation", async ({ page }) => {
  const name = uniqueName("AL-02");
  await startEventRule(page, name);
  await dialog(page).getByRole("button", { name: "Zapisz" }).click();

  await rule(page, name).getByRole("button", { name: "Wyłącz" }).click();
  await expect(rule(page, name)).toContainText("wyłączona");
  await rule(page, name).getByRole("button", { name: "Włącz" }).click();
  await expect(rule(page, name)).toContainText("działa");

  await rule(page, name).getByRole("button", { name: "Usuń…" }).click();
  await dialog(page).getByRole("button", { name: "Usuń" }).click();
  await expect(rule(page, name)).toHaveCount(0);
});

test("AL-03 the package refuses a message that names a slot the rule does not have, at the field", async ({ page }) => {
  const name = uniqueName("AL-03");
  await startEventRule(page, name);
  await dialog(page).getByLabel("Treść wiadomości").fill("{nie_ma_takiego}");

  await dialog(page).getByRole("button", { name: "Zapisz" }).click();

  await expect(dialog(page)).toContainText("nie_ma_takiego");
  await expect(dialog(page)).toBeVisible();
  await dialog(page).getByRole("button", { name: "Cancel" }).click();
  await expect(rule(page, name)).toHaveCount(0);
});
