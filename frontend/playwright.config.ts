import { defineConfig, devices } from "@playwright/test";

/**
 * E2E against the live local stack (frontend :3100 + backend :3000) — both must
 * be running. Auth uses ROTATING refresh tokens, so a shared session can't be
 * reused across tests (reuse → family revoke). Instead each authenticated test
 * logs in fresh via the API (see e2e/helpers.ts), getting its own token family.
 */
const BASE_URL = process.env.E2E_BASE_URL || "http://localhost:3100";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  // The local dev backend is a single node doing heavy cross-tenant KPI
  // aggregations; cap concurrency so workers don't time each other out.
  workers: 2,
  forbidOnly: !!process.env.CI,
  retries: 1,
  reporter: [["list"]],
  timeout: 30_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    actionTimeout: 10_000,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
