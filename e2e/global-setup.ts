/**
 * Playwright global setup — runs once before all tests.
 *
 * Logs in with test credentials (E2E_TEST_EMAIL / E2E_TEST_PASSWORD) and
 * saves the Supabase session to e2e/.auth/user.json so individual tests
 * can reuse it via storageState without re-authenticating each time.
 *
 * If the env vars are not set the file is written as an empty state and
 * individual test files must handle auth themselves.
 */
import { chromium, FullConfig } from "@playwright/test";
import * as path from "path";
import * as fs from "fs";

export const AUTH_FILE = path.join(__dirname, ".auth", "user.json");

export default async function globalSetup(_config: FullConfig) {
  // Ensure the .auth directory exists
  const authDir = path.dirname(AUTH_FILE);
  if (!fs.existsSync(authDir)) fs.mkdirSync(authDir, { recursive: true });

  const email = process.env.E2E_TEST_EMAIL;
  const password = process.env.E2E_TEST_PASSWORD;

  if (!email || !password) {
    // Write an empty storage state so tests can still run (they'll hit /login)
    fs.writeFileSync(AUTH_FILE, JSON.stringify({ cookies: [], origins: [] }));
    return;
  }

  const browser = await chromium.launch();
  const page = await browser.newPage();

  await page.goto("http://localhost:3000/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();

  // Wait for redirect to /tests after successful login
  await page.waitForURL("**/tests", { timeout: 15_000 });

  await page.context().storageState({ path: AUTH_FILE });
  await browser.close();
}
