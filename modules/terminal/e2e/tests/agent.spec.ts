import { expect, test, type Page } from "@playwright/test";
import { createStrategy, documentText, openStrategy, replaceEditorText, strategyDocument, uniqueName } from "../support";

/**
 * The strategy's chat with the agent, answered by `e2e/agent-scenario.json` instead of a model (`agent-simulated-model`):
 * what is simulated is only what to say; the tools write to the real database and the terminal reads them back.
 */

const chat = (page: Page) => page.getByRole("complementary", { name: "Czat strategii" });

async function say(page: Page, message: string, reply: string): Promise<void> {
  await chat(page).getByRole("textbox", { name: "Message the agent" }).fill(message);
  await chat(page).getByRole("textbox", { name: "Message the agent" }).press("Enter");
  await expect(chat(page)).toContainText(reply, { timeout: 15_000 });
}

test("AG-01 a strategy described in the chat arrives as a draft, is saved, and keeps its conversation", async ({ page, request }) => {
  const name = uniqueName("AG-01");
  await page.goto("/strategies");
  await page.getByRole("button", { name: "Nowa…" }).click();

  await say(page, `E2E nowa: ${name}`, "Wpisałem szkic nowej strategii do edytora.");
  await expect(page.getByText("Agent wpisał zmianę do edytora")).toBeVisible();
  await expect(page.locator(".cm-content")).toContainText(name);
  await page.getByRole("button", { name: "Zapisz", exact: true }).click();

  await expect(page.getByRole("heading", { name: new RegExp(`${name} · rewizja 1`) })).toBeVisible();
  await expect
    .poll(async () => {
      const listed = (await (await request.get("/strategies-api/strategies?archived=false")).json()) as {
        name: string;
        conversation_id: number | null;
      }[];
      return listed.find((s) => s.name === name)?.conversation_id ?? null;
    })
    .not.toBeNull();
});

test("AG-02 the agent's draft lands in the editor unsaved and is discarded for good", async ({ page, request }) => {
  const name = uniqueName("AG-02");
  const id = await createStrategy(request, strategyDocument(name));
  await openStrategy(page, name);

  await say(page, `E2E szkic ${id}`, "Wpisałem szersze stopy do edytora.");
  await expect(page.locator(".cm-content")).toContainText('"default": 70');
  await expect(page.getByText("niezapisane zmiany")).toBeVisible();
  await page.getByRole("button", { name: "Porzuć zmiany" }).click();
  await expect(page.locator(".cm-content")).toContainText('"default": 50');

  await openStrategy(page, name);
  await expect(page.locator(".cm-content")).toContainText('"default": 50');
});

test("AG-03 a model picked in the strategy's chat stays picked across a turn and a reopen", async ({ page, request }) => {
  const name = uniqueName("AG-03");
  await createStrategy(request, strategyDocument(name));
  await openStrategy(page, name);
  const picker = chat(page).getByLabel("Model");

  await picker.selectOption("e2e-sol");
  await say(page, "E2E ping", "pong");
  await expect(picker).toHaveValue("e2e-sol");
  await expect(chat(page)).not.toContainText("no such session");

  await openStrategy(page, name);
  await expect(picker).toHaveValue("e2e-sol");
});

test("AG-04 a revision the agent saves leaves the operator's unsaved edit in place", async ({ page, request }) => {
  const name = uniqueName("AG-04");
  const id = await createStrategy(request, strategyDocument(name));
  await openStrategy(page, name);
  await replaceEditorText(page, documentText(strategyDocument(name, { entries: [{ side: "long", when: "hour == 10" }] })));

  await say(page, `E2E zapisz ${id} na 1`, "Zapisałem nową rewizję.");

  await expect(page.getByRole("status")).toContainText("Istnieje nowsza rewizja 2");
  await expect(page.locator(".cm-content")).toContainText("hour == 10");
});
