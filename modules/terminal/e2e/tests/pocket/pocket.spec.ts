import { expect, test, type Page } from "@playwright/test";

/** The pocket on a phone-sized screen, reading what `seed.py` wrote and asking the simulated agent. Read-only: the terminal's tests change the same rows. */

const screen = (page: Page, name: string) => page.getByRole("navigation", { name: "Screens" }).getByRole("button", { name });

test("PK-01 opens on the markets and shows a tracked event with its collection state", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Polymarket" })).toBeVisible();
  await expect(page.getByRole("article").filter({ hasText: "E2E keep event" })).toContainText("stalled");
});

test("PK-02 moves between screens and reads the scored post", async ({ page }) => {
  await page.goto("/");

  await screen(page, "Posts").click();

  await expect(page.getByRole("heading", { name: "Posts" })).toBeVisible();
  await expect(page.getByText("E2E scored post about rates")).toBeVisible();
});

test("PK-03 filters the headlines by a word", async ({ page }) => {
  await page.goto("/");
  await screen(page, "News").click();
  await expect(page.getByText("E2E Hormuz headline")).toBeVisible();

  await page.getByRole("searchbox", { name: "Filter headlines" }).fill("tankers");

  await expect(page.getByText("E2E Hormuz headline")).toBeVisible();
  await expect(page.getByText("E2E Budget headline")).toHaveCount(0);
});

test("PK-04 asks the agent and reads the answer", async ({ page }) => {
  await page.goto("/");
  await screen(page, "Agent").click();

  await page.getByRole("textbox", { name: /Ask the agent/ }).fill("E2E ping");
  // Enter is a new line on a phone; sending is the button.
  await page.getByRole("button", { name: "Send" }).click();

  await expect(page.getByText("pong")).toBeVisible({ timeout: 15_000 });
});
