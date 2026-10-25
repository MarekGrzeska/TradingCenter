import { expect, test, type Page } from "@playwright/test";
import { uniqueName } from "../support";

/** The conversation panel every tab carries, answered by `e2e/agent-scenario.json` (`E2E ping` → `pong`). */

const panel = (page: Page) => page.getByRole("complementary", { name: "Agent chat" });

async function openPanel(page: Page): Promise<void> {
  await page.goto("/instruments");
  const open = page.getByRole("button", { name: "Open agent chat" });
  if (await open.isVisible()) await open.click();
  await expect(panel(page)).toBeVisible();
}

async function ping(page: Page): Promise<void> {
  await panel(page).getByRole("textbox", { name: "Message the agent" }).fill("E2E ping");
  await panel(page).getByRole("textbox", { name: "Message the agent" }).press("Enter");
  await expect(panel(page)).toContainText("pong", { timeout: 15_000 });
}

test("AP-01 a conversation gets a title, is renamed in the list and opens again with its messages", async ({ page }) => {
  await openPanel(page);
  await ping(page);
  const renamed = uniqueName("AP-01");

  await panel(page).getByRole("button", { name: "Conversations" }).click();
  await panel(page).getByRole("button", { name: /^Rename / }).first().click();
  await panel(page).getByRole("textbox", { name: /^Rename / }).fill(renamed);
  await panel(page).getByRole("textbox", { name: /^Rename / }).press("Enter");
  await expect(panel(page).getByRole("button", { name: renamed, exact: true })).toBeVisible();

  await page.reload();
  await openPanel(page);
  await panel(page).getByRole("button", { name: "Conversations" }).click();
  await panel(page).getByRole("button", { name: renamed, exact: true }).click();
  await expect(panel(page)).toContainText("pong");
});

test("AP-02 a conversation is deleted only after the confirmation, and not when kept", async ({ page }) => {
  await openPanel(page);
  await ping(page);
  const renamed = uniqueName("AP-02");
  await panel(page).getByRole("button", { name: "Conversations" }).click();
  await panel(page).getByRole("button", { name: /^Rename / }).first().click();
  await panel(page).getByRole("textbox", { name: /^Rename / }).fill(renamed);
  await panel(page).getByRole("textbox", { name: /^Rename / }).press("Enter");

  await panel(page).getByRole("button", { name: `Delete ${renamed}` }).click();
  await panel(page).getByRole("button", { name: "Keep" }).click();
  await expect(panel(page).getByRole("button", { name: renamed, exact: true })).toBeVisible();

  await panel(page).getByRole("button", { name: `Delete ${renamed}` }).click();
  await panel(page).getByRole("button", { name: "Delete", exact: true }).click();
  await expect(panel(page).getByRole("button", { name: renamed, exact: true })).toHaveCount(0);
});
