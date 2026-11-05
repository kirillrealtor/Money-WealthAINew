import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { loginDemo } from "./helpers";

/** Fail on serious/critical accessibility violations (WCAG 2.2 AA gate). */
async function scan(page: import("@playwright/test").Page) {
  // Scan settled content: halfway through an opacity entrance animation even
  // high-contrast text is temporarily blended into its background. Ignore
  // decorative infinite animations so this cannot wait forever on a backdrop.
  await page.evaluate(async () => {
    await Promise.all(document.getAnimations()
      .filter((animation) => animation.effect?.getTiming().iterations !== Infinity)
      .map((animation) => animation.finished.catch(() => undefined)));
  });
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  return results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
}

test.describe("accessibility (axe)", () => {
  test("landing has no serious/critical violations", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    const violations = await scan(page);
    expect(violations, JSON.stringify(violations.map((v) => v.id), null, 2)).toEqual([]);
  });

  test("login has no serious/critical violations", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByLabel("Email")).toBeVisible();
    const violations = await scan(page);
    expect(violations, JSON.stringify(violations.map((v) => v.id), null, 2)).toEqual([]);
  });

  test("dashboard has no serious/critical violations", async ({ page }) => {
    await loginDemo(page);
    await page.goto("/app");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    const violations = await scan(page);
    expect(violations, JSON.stringify(violations.map((v) => v.id), null, 2)).toEqual([]);
  });

  test("purchase planner assessment has no serious/critical violations", async ({ page }) => {
    await loginDemo(page);
    await page.goto("/app/purchases");
    await page.getByRole("button", { name: "Check affordability" }).click();
    await expect(page.getByRole("checkbox")).toBeVisible();
    const violations = await scan(page);
    expect(violations, JSON.stringify(violations.map((v) => v.id), null, 2)).toEqual([]);
  });
});
