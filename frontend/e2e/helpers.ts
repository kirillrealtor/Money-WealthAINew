import { type Page, expect } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

const DEMO_EMAIL = "demo@fathom.app";
const API_BASE = process.env.E2E_API_BASE_URL || "http://localhost:3000";

/** Never log this value: local setup generates a dedicated synthetic-profile password. */
export function demoPassword() {
  if (process.env.E2E_DEMO_PASSWORD) return process.env.E2E_DEMO_PASSWORD;
  const file = path.resolve(process.cwd(), "../backend/.env");
  const env = existsSync(file) ? readFileSync(file, "utf8") : "";
  return env.match(/^DEMO_PASSWORD=["']?([^\r\n"']+)/m)?.[1] ?? "WealthDemo123!";
}

/** A fresh token family per test avoids rotating-cookie reuse across parallel pages. */
export async function loginDemo(page: Page) {
  const config = await page.request.get(`${API_BASE}/api/v1/auth/config`);
  expect(config.ok(), "backend auth configuration should be reachable").toBeTruthy();
  if ((await config.json()).auth_mode === "password") {
    const login = await page.request.post("/api/auth/login", {
      data: { email: DEMO_EMAIL, password: demoPassword() },
    });
    expect(login.ok(), "seeded local demo login should succeed").toBeTruthy();
    return;
  }

  const request = await page.request.post("/api/auth/magic-link", { data: { email: DEMO_EMAIL } });
  expect(request.ok(), "magic-link request should succeed").toBeTruthy();

  const peek = await page.request.get(
    `${API_BASE}/api/v1/auth/dev/peek-magic-link?email=${encodeURIComponent(DEMO_EMAIL)}`,
  );
  expect(peek.ok(), "dev peek-magic-link should succeed").toBeTruthy();
  const { token } = (await peek.json()) as { token: string };

  const verify = await page.request.get(`/api/auth/verify-email?token=${encodeURIComponent(token)}`);
  expect(verify.ok(), "verify-email should succeed").toBeTruthy();
}
