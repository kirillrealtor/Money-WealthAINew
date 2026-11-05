import { expect, test, type Page } from "@playwright/test";

const id = "00000000-0000-0000-0000-000000000002";
const purchase = {
  purchase_id: id, description: "Noise-cancelling headphones", amount: "149.00", currency: "USD",
  sandbox: true, status: "ASSESSED", order_id: null, approval_url: null, capture_id: null,
  assessment: { recommendation: "ok", liquid_assets: "9000.00", monthly_spend: "1500.00",
    post_purchase_liquid: "8851.00", emergency_fund_flag: false, note: "Educational estimate; not financial advice." },
};

async function mockSession(page: Page) {
  await page.route("**/api/auth/refresh", (route) => route.fulfill({ json: { access_token: "test-token" } }));
  await page.route("**/api/backend/auth/me", (route) => route.fulfill({ json: {
    user_id: "test-user", email: "demo@example.com", full_name: "Demo User", tier: "free",
    advisor_persona: "balanced", is_verified: true, onboarding_step: 3,
  } }));
  await page.route("**/api/backend/notifications", (route) => route.fulfill({ json: { items: [], unread_count: 0 } }));
  await page.route("**/api/backend/paypal/config", (route) => route.fulfill({ json: { configured: true, sandbox: true } }));
}

test.beforeEach(async ({ page }) => { await mockSession(page); });

test("assessment, AI explanation and explicit checkout acknowledgement", async ({ page }, testInfo) => {
  let orderRequests = 0;
  await page.route("**/api/backend/paypal/assess", (route) => route.fulfill({ json: purchase }));
  await page.route("**/api/backend/advisor/chat", (route) => route.fulfill({ json: {
    chat_id: "chat", message_id: "message", response: "Your remaining cash is $8,851. This is educational analysis.",
    tool_calls_made: ["calculate_affordability"], provider: "test-provider", tokens_used: 50,
  } }));
  await page.route("**/api/backend/paypal/orders", (route) => {
    orderRequests++;
    expect(route.request().postDataJSON()).toEqual({ purchase_id: id, acknowledge: true });
    return route.fulfill({ json: { ...purchase, status: "CREATED", order_id: "ORDER123",
      approval_url: "https://www.sandbox.paypal.com/checkoutnow?token=ORDER123" } });
  });
  await page.route("https://www.sandbox.paypal.com/**", (route) => route.fulfill({ body: "Sandbox approval stub" }));
  await page.goto("/app/purchases");
  await page.getByRole("button", { name: "Check affordability" }).click();
  const checkout = page.getByRole("button", { name: "Continue to PayPal sandbox" });
  await expect(checkout).toBeDisabled();
  await page.getByRole("button", { name: "Explain this purchase" }).click();
  await expect(page.getByText(/Tools: calculate_affordability/)).toBeVisible();
  expect(orderRequests).toBe(0);
  await page.getByRole("checkbox").check();
  await page.screenshot({ path: testInfo.outputPath("purchase-planner.png"), fullPage: true });
  await checkout.click();
  await expect(page).toHaveURL(/www\.sandbox\.paypal\.com\/checkoutnow/);
  expect(orderRequests).toBe(1);
});

test("insufficient data blocks checkout even after acknowledgement", async ({ page }) => {
  await page.route("**/api/backend/paypal/assess", (route) => route.fulfill({ json: {
    ...purchase, assessment: { ...purchase.assessment, recommendation: "insufficient_data" },
  } }));
  await page.goto("/app/purchases");
  await page.getByRole("button", { name: "Check affordability" }).click();
  await expect(page.getByText("More financial data needed")).toBeVisible();
  await page.getByRole("checkbox").check();
  await expect(page.getByRole("button", { name: "Continue to PayPal sandbox" })).toBeDisabled();
});

test("return and cancellation do not capture until user confirms", async ({ page }) => {
  let captureRequests = 0;
  await page.route(`**/api/backend/paypal/purchases/${id}`, (route) => route.fulfill({ json: {
    ...purchase, status: "CREATED", order_id: "ORDER123",
  } }));
  await page.route(`**/api/backend/paypal/purchases/${id}/capture`, (route) => {
    captureRequests++;
    return route.fulfill({ json: { ...purchase, status: "COMPLETED", order_id: "ORDER123", capture_id: "CAPTURE123" } });
  });
  await page.goto(`/app/purchases?purchase_id=${id}&cancelled=1`);
  await expect(page.getByText("Checkout was cancelled. No payment has been confirmed.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Confirm sandbox payment" })).toBeVisible();
  expect(captureRequests).toBe(0);
  await page.getByRole("button", { name: "Confirm sandbox payment" }).click();
  await expect(page.getByText(/Sandbox payment confirmed/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Confirm sandbox payment" })).toHaveCount(0);
  expect(captureRequests).toBe(1);
});

test("pending capture stays pending and allows a later status check", async ({ page }) => {
  await page.route(`**/api/backend/paypal/purchases/${id}`, (route) => route.fulfill({ json: {
    ...purchase, status: "CREATED", order_id: "ORDER123",
  } }));
  await page.route(`**/api/backend/paypal/purchases/${id}/capture`, (route) => route.fulfill({ json: {
    ...purchase, status: "PENDING", order_id: "ORDER123", capture_id: "PENDING123",
  } }));
  await page.goto(`/app/purchases?purchase_id=${id}`);
  await page.getByRole("button", { name: "Confirm sandbox payment" }).click();
  await expect(page.getByText("PayPal is processing this payment. Check again shortly.")).toBeVisible();
  await expect(page.getByText(/Sandbox payment confirmed/)).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Confirm sandbox payment" })).toBeEnabled();
});
