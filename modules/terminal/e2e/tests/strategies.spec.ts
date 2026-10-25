import { expect, test, type APIRequestContext } from "@playwright/test";

/** The Strategies tab against a live workbench: what is set up goes through REST, what is checked is on screen. */

async function createStrategy(request: APIRequestContext, name: string): Promise<number> {
  const document = {
    schema: 1,
    name,
    symbol: "US100",
    timeframe: "HOUR",
    entries: [{ side: "long", when: "hour == 9" }],
    exits: { stop: "entry_price - 50", target: "entry_price + 50" },
    sizing: { mode: "fixed_units", value: 1 },
  };
  const response = await request.post("/strategies-api/strategies", { data: document });
  expect(response.ok()).toBeTruthy();
  return (await response.json()).strategy_id;
}

test("ST-01 opens a strategy from the list with its editor, chat and summary", async ({ page, request }) => {
  const name = `ST-01 ${Date.now()}`;
  await createStrategy(request, name);

  await page.goto("/strategies");
  await page.getByRole("button", { name: new RegExp(name) }).click();

  await expect(page.getByText(/rewizja 1/)).toBeVisible();
  await expect(page.getByRole("complementary", { name: "Czat strategii" })).toBeVisible();
  await expect(page.locator(".cm-content")).toContainText(name);
});
