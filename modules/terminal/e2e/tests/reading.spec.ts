import { expect, test } from "@playwright/test";
import { uniqueName } from "../support";

/** The archives' screens, read from rows `seed.py` wrote: nothing is collected from the network, so a screen shows what it was given. */

test("SO-01 opens the scored post and folds the unread one away until asked", async ({ page }) => {
  await page.goto("/social");

  await expect(page.getByText("E2E scored post about rates")).toBeVisible();
  await expect(page.getByText("9/10")).toBeVisible();
  await expect(page.getByText("E2E unread post about nothing")).toHaveCount(0);

  await page.getByRole("button", { name: /Pozostałe posty \(1\)/ }).click();
  await expect(page.getByText("E2E unread post about nothing")).toBeVisible();
});

test("NW-01 narrows the headlines by a word in the title or the lead", async ({ page }) => {
  await page.goto("/news");
  await expect(page.getByText("E2E Hormuz headline")).toBeVisible();
  await expect(page.getByText("E2E Budget headline")).toBeVisible();

  await page.getByRole("searchbox", { name: "szukaj w newsach" }).fill("tankers");

  await expect(page.getByText("E2E Hormuz headline")).toBeVisible();
  await expect(page.getByText("E2E Budget headline")).toHaveCount(0);
});

test("NW-02 keeps a headline and finds it again among the kept", async ({ page }) => {
  await page.goto("/news");
  const card = page.getByRole("article").filter({ hasText: "E2E Budget headline" });

  await card.getByRole("button", { name: "zachowaj" }).click();
  await expect(card.getByRole("button", { name: "zachowany" })).toBeVisible();

  await page.getByRole("button", { name: "zachowane", exact: true }).click();
  await expect(page.getByText("E2E Budget headline")).toBeVisible();
  await expect(page.getByText("E2E Hormuz headline")).toHaveCount(0);
});

test("PM-01 says the event's collection stalled, shows its price and files it in a group made on the screen", async ({ page }) => {
  const group = uniqueName("pm");
  await page.goto("/polymarket");
  const card = page.getByRole("article").filter({ hasText: "E2E keep event" });
  await expect(card).toContainText("stalled");
  await card.getByRole("button", { name: /E2E keep event/ }).click();
  await expect(card).toContainText("62.0%");

  await page.getByRole("button", { name: "New group" }).click();
  await page.getByRole("dialog").getByRole("textbox", { name: "Name" }).fill(group);
  await page.getByRole("dialog").getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("button", { name: new RegExp(`^${group} \\(0\\)`) })).toBeVisible();

  // Making a group selects it, and a group with nothing in it shows nothing.
  await page.getByRole("button", { name: "all", exact: true }).click();
  await card.getByLabel("Group for E2E keep event").selectOption({ label: group });
  await expect(page.getByRole("button", { name: new RegExp(`^${group} \\(1\\)`) })).toBeVisible();
});

test("PM-02 removes an observation only after the warning is confirmed", async ({ page }) => {
  await page.goto("/polymarket");
  const card = page.getByRole("article").filter({ hasText: "E2E drop event" });

  await card.getByRole("button", { name: "Remove" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();
  await expect(card).toBeVisible();

  await card.getByRole("button", { name: "Remove" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Remove" }).click();
  await expect(page.getByText("E2E drop event")).toHaveCount(0);
});
