import { test, expect, type Page } from "@playwright/test";
import { loginDemo } from "./helpers";

test.beforeEach(async ({ page }) => {
  await loginDemo(page);
});

async function deleteBudgetIfExists(page: Page, label: string) {
  const card = page.locator("div.glass").filter({ hasText: label });
  if ((await card.count()) === 0) return;
  await card.first().hover();
  await card.first().getByRole("button", { name: "Delete budget" }).click();
  await expect(page.getByText(`${label} budget deleted`)).toBeVisible();
}

test.describe("authenticated app", () => {
  test("dashboard loads with greeting and summaries", async ({ page }) => {
    await page.goto("/app");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Net worth", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "View linked accounts" })).toBeVisible();
    await expect(page.getByText("$16,500.00", { exact: true }).first()).toBeVisible();
  });

  test("budgets render; can create and delete one", async ({ page }) => {
    await page.goto("/app/budgets");
    await expect(page.getByText("Food And Drink")).toBeVisible();

    await deleteBudgetIfExists(page, "Travel"); // clean slate for re-runs

    await page.getByRole("button", { name: "New budget" }).click();
    await page.getByLabel("Category").selectOption("TRAVEL");
    await page.locator("#limit").fill("250");
    await page.getByRole("button", { name: "Create budget" }).click();

    await expect(page.getByText("Travel budget created")).toBeVisible();
    await expect(page.locator("div.glass").filter({ hasText: "Travel" }).first()).toBeVisible();

    await deleteBudgetIfExists(page, "Travel"); // cleanup
  });

  test("goals page shows the seeded goals", async ({ page }) => {
    await page.goto("/app/goals");
    await expect(page.getByText("Synthetic emergency fund", { exact: true })).toBeVisible();
  });

  test("accounts page distinguishes synthetic data from a Plaid connection", async ({ page }) => {
    await page.goto("/app/accounts");
    await expect(page.getByText("Synthetic Checking", { exact: true })).toBeVisible();
    await expect(page.getByText("Synthetic data - no Plaid connection", { exact: true })).toBeVisible();
  });

  test("debt and portfolio show seeded financial data", async ({ page }) => {
    await page.goto("/app/debt");
    await expect(page.getByText("Total debt")).toBeVisible();
    await page.goto("/app/portfolio");
    await expect(page.getByText("Total value")).toBeVisible();
  });

  test("settings shows profile + billing", async ({ page }) => {
    await page.goto("/app/settings");
    await expect(page.getByText("Plan & billing")).toBeVisible();
    await expect(page.getByText("Quiet hours")).toBeVisible();
  });

  test("advisor page shows the composer and prompts", async ({ page }) => {
    await page.goto("/app/advisor");
    await expect(page.getByPlaceholder(/Ask about your budgets/i)).toBeVisible();
    await expect(page.getByText(/ask me anything about your/i)).toBeVisible();
  });

  test("unauthenticated visit to /app redirects to login", async ({ browser }) => {
    // Fresh context with NO storageState → no session cookie.
    const ctx = await browser.newContext({ storageState: { cookies: [], origins: [] } });
    const page = await ctx.newPage();
    await page.goto("/app");
    await expect(page).toHaveURL(/\/login/);
    await ctx.close();
  });
});
