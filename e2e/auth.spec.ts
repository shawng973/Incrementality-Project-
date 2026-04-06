/**
 * E2E: Authentication flow
 *
 * Tests login page UI, error handling, and redirect behaviour.
 * Uses Supabase auth route mocks so no live Supabase project is required.
 */
import { test, expect } from "@playwright/test";

// Mock Supabase auth API so tests run without a live project
async function mockSupabaseAuth(page, { succeed }: { succeed: boolean }) {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "https://test.supabase.co";

  await page.route(`${supabaseUrl}/auth/v1/token**`, async (route) => {
    if (succeed) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          access_token: "fake-access-token",
          token_type: "bearer",
          expires_in: 3600,
          refresh_token: "fake-refresh-token",
          user: { id: "user-001", email: "test@agency.com" },
        }),
      });
    }
    return route.fulfill({
      status: 400,
      contentType: "application/json",
      body: JSON.stringify({ error: "invalid_grant", error_description: "Invalid login credentials" }),
    });
  });
}

test.describe("Login page", () => {
  test("shows the login form on /login", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "Incremental Tool" })).toBeVisible();
    await expect(page.getByLabel("Email")).toBeVisible();
    await expect(page.getByLabel("Password")).toBeVisible();
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  });

  test("shows error message on invalid credentials", async ({ page }) => {
    await mockSupabaseAuth(page, { succeed: false });
    await page.goto("/login");

    await page.getByLabel("Email").fill("wrong@agency.com");
    await page.getByLabel("Password").fill("wrongpassword");
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page.getByRole("alert")).toBeVisible();
  });

  test("Sign in button shows loading state while submitting", async ({ page }) => {
    // Don't resolve the auth call immediately — check loading state
    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "https://test.supabase.co";
    let resolveAuth: (() => void) | null = null;
    await page.route(`${supabaseUrl}/auth/v1/token**`, async (route) => {
      await new Promise<void>((res) => { resolveAuth = res; });
      route.fulfill({ status: 400, body: "{}" });
    });

    await page.goto("/login");
    await page.getByLabel("Email").fill("test@agency.com");
    await page.getByLabel("Password").fill("password");

    const button = page.getByRole("button", { name: /sign in/i });
    await button.click();

    // Button should be disabled (loading) immediately after click
    await expect(button).toBeDisabled();
    resolveAuth?.();
  });

  test("unauthenticated visit to /tests redirects to /login", async ({ page }) => {
    // Navigate directly without auth; middleware should redirect
    await page.goto("/tests");
    await expect(page).toHaveURL(/login/);
  });
});
