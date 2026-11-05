import { test, expect } from "@playwright/test";

test.describe("marketing / public", () => {
  test("landing renders the hero and CTAs", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("understand");
    await expect(page.getByRole("link", { name: /Start free/i }).first()).toBeVisible();
  });

  test("pricing page: billing toggle and FAQ work", async ({ page }) => {
    await page.goto("/pricing");
    await expect(page.getByText("Most popular")).toBeVisible();
    // toggle annual <-> monthly
    const toggle = page.getByRole("switch", { name: /annual billing/i });
    await toggle.click();
    // FAQ accordion opens
    const faq = page.getByText("Is there really a free plan?");
    await faq.click();
    await expect(page.getByText(/no card required to start/i)).toBeVisible();
  });

  test("unknown route shows the branded 404", async ({ page }) => {
    const res = await page.goto("/this-page-does-not-exist");
    expect(res?.status()).toBe(404);
    await expect(page.getByText("404")).toBeVisible();
    await expect(page.getByRole("link", { name: /Back home/i })).toBeVisible();
  });

  test("security page lists trust pillars", async ({ page }) => {
    await page.goto("/security");
    await expect(page.getByText("Read-only banking")).toBeVisible();
    await expect(page.getByText(/AES-256-GCM/i)).toBeVisible();
  });
});
