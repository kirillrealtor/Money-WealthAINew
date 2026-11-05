import { test, expect } from "@playwright/test";

// Admin is a separate identity (in-memory token, no shared cookie) — log in fresh.
test.describe("admin console", () => {
  test("super-admin can sign in and see KPIs", async ({ page }) => {
    test.skip(!process.env.E2E_ADMIN_PASSWORD, "Requires an explicitly provisioned test admin account");
    await page.goto("/admin/login");
    await page.locator("#email").fill(process.env.E2E_ADMIN_EMAIL ?? "admin@fathom.app");
    await page.locator("#password").fill(process.env.E2E_ADMIN_PASSWORD!);
    await page.getByRole("button", { name: "Sign in" }).click();

    await page.waitForURL("**/admin", { timeout: 15_000 });
    await expect(page.getByText("Total users")).toBeVisible();
    await expect(page.getByText("MoneyWealth AI Admin")).toBeVisible();
  });

  test("admin can browse users", async ({ page }) => {
    test.skip(!process.env.E2E_ADMIN_PASSWORD, "Requires an explicitly provisioned test admin account");
    await page.goto("/admin/login");
    await page.locator("#email").fill(process.env.E2E_ADMIN_EMAIL ?? "admin@fathom.app");
    await page.locator("#password").fill(process.env.E2E_ADMIN_PASSWORD!);
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.waitForURL("**/admin");

    await page.getByRole("link", { name: "Users" }).click();
    await expect(page).toHaveURL(/\/admin\/users/);
    await expect(page.getByPlaceholder(/Search by email/i)).toBeVisible();
  });

  test("unauthenticated admin route redirects to admin login", async ({ page }) => {
    await page.goto("/admin/users");
    await expect(page).toHaveURL(/\/admin\/login/);
  });
});
