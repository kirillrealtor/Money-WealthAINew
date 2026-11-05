/** Local-stack smoke test. Uses seeded data and actual backend/MCP; no mocked API routes. */
import { expect, test } from "@playwright/test";
import { loginDemo } from "./helpers";

test("seeded purchase assessment and simulated advisor cross real MCP", async ({ page }) => {
  test.setTimeout(90_000);
  await loginDemo(page);
  await page.goto("/app/purchases");
  await expect(page.getByText(/Synthetic demo finances/)).toBeVisible();
  await page.getByRole("button", { name: "Check affordability" }).click();
  await expect(page.getByText("$12,000.00", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("$11,851.00", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "Explain this purchase" }).click();
  await expect(page.getByText(/Provider: mock. Tools: calculate_affordability/)).toBeVisible({ timeout: 45_000 });
  await expect(page.getByText("Simulated advisor response for development. No live AI model was called.")).toBeVisible();
  await page.getByRole("checkbox").check();
  // Live checkout is deliberately unavailable until actual sandbox credentials are supplied.
  await expect(page.getByRole("button", { name: "Continue to PayPal sandbox" })).toBeDisabled();
});
