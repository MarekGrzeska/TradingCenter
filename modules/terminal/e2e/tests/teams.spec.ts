import { expect, test, type Page } from "@playwright/test";
import { uniqueName } from "../support";

/** The Teams tab against a live workbench. No model answers (`TEAMS_OPENAI_API_KEY` leads to 127.0.0.1:9), so nothing here runs a team. */

const team = (page: Page, name: string) => page.getByRole("listitem").filter({ hasText: name });

async function startTeam(page: Page, name: string): Promise<void> {
  await page.goto("/teams");
  await page.getByRole("button", { name: "New team" }).click();
  await page.getByRole("textbox", { name: "Team name" }).fill(name);
  await page.getByRole("textbox", { name: "Team description" }).fill("e2e");
}

async function giveGuidance(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Settings for New role" }).click();
  await page.getByLabel("Prompt", { exact: true }).fill("Say what you see.");
  await page.getByRole("button", { name: "Close" }).click();
}

test("TM-01 a team made in the editor is saved as revision 1 and listed in the catalogue", async ({ page }) => {
  const name = uniqueName("TM-01");
  await startTeam(page, name);
  await giveGuidance(page);

  await page.getByRole("button", { name: "Create team" }).click();

  await expect(page.getByText("revision 1").first()).toBeVisible();
  await page.getByRole("button", { name: "← Catalogue" }).click();
  await expect(team(page, name)).toContainText("revision 1");
});

test("TM-02 refuses an agent with no prompt and saves nothing", async ({ page }) => {
  const name = uniqueName("TM-02");
  await startTeam(page, name);

  await page.getByRole("button", { name: "Create team" }).click();

  await expect(page.getByText("agent prompt must not be blank").first()).toBeVisible();
  await page.getByRole("button", { name: "← Catalogue" }).click();
  await expect(team(page, name)).toHaveCount(0);
});

test("TM-03 saves a changed team as the next revision and retires it out of the catalogue", async ({ page }) => {
  const name = uniqueName("TM-03");
  await startTeam(page, name);
  await giveGuidance(page);
  await page.getByRole("button", { name: "Create team" }).click();
  await expect(page.getByText("revision 1").first()).toBeVisible();

  await page.getByRole("button", { name: "Settings for New role" }).click();
  await page.getByLabel("Prompt", { exact: true }).fill("Say what you see, briefly.");
  await page.getByRole("button", { name: "Close" }).click();
  await page.getByRole("button", { name: "Save revision" }).click();
  await expect(page.getByText("revision 2").first()).toBeVisible();

  await page.getByRole("button", { name: "← Catalogue" }).click();
  await expect(team(page, name)).toContainText("revision 2");
  await team(page, name).getByRole("button", { name: "Retire" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Retire" }).click();
  await expect(team(page, name)).toHaveCount(0);
});
