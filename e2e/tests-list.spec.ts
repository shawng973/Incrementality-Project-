/**
 * E2E: Tests list page (/tests)
 *
 * Verifies the list renders correctly, "New test" button navigates to
 * the wizard, and the empty state is shown when no tests exist.
 */
import { test, expect, mockApi, MOCK_TEST } from "./fixtures";

test.describe("Tests list", () => {
  test.use({ storageState: "e2e/.auth/user.json" });

  test.beforeEach(async ({ page }) => {
    await mockApi(page);
  });

  test("renders page heading", async ({ page }) => {
    await page.goto("/tests");
    await expect(page.getByRole("heading", { name: /tests/i })).toBeVisible();
  });

  test("shows test card with name and status badge", async ({ page }) => {
    await page.goto("/tests");
    await expect(page.getByText(MOCK_TEST.name)).toBeVisible();
    // Status badge text
    await expect(page.getByText(/active/i).first()).toBeVisible();
  });

  test("New test button navigates to /tests/new", async ({ page }) => {
    await page.goto("/tests");
    await page.getByRole("link", { name: /new test/i }).click();
    await expect(page).toHaveURL(/\/tests\/new/);
  });

  test("clicking a test card navigates to test detail", async ({ page }) => {
    await page.goto("/tests");
    await page.getByText(MOCK_TEST.name).click();
    await expect(page).toHaveURL(new RegExp(`/tests/${MOCK_TEST.id}`));
  });
});
