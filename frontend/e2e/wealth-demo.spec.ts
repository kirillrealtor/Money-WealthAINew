/** Local-stack smoke test. Uses seeded data and actual backend/MCP; no mocked API routes. */
import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

test("seeded purchase assessment and simulated advisor cross real MCP", async ({ page }) => {
  test.setTimeout(90_000);
  // Read only the local test password; never print it or include it in screenshots.
  const env = readFileSync(path.resolve(process.cwd(), "../backend/.env"), "utf8");
  const fromFile = env.match(/^DEMO_PASSWORD=["']?([^\r\n"']+)/m)?.[1];
  const password = process.env.E2E_DEMO_PASSWORD ?? fromFile ?? "WealthDemo123!";
  const login = await page.request.post("/api/auth/login", { data: { email: "demo@fathom.app", password } });
  expect(login.status(), "seeded local demo login").toBe(200);
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
