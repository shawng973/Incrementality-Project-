/**
 * E2E: Create test wizard (/tests/new)
 *
 * Critical path: fill Step 1 → Step 2 → Step 3 review → submit → redirects
 * to the new test's detail page.
 */
import { test, expect, mockApi, MOCK_TEST } from "./fixtures";

test.describe("Create test wizard", () => {
  test.use({ storageState: "e2e/.auth/user.json" });

  test.beforeEach(async ({ page }) => {
    await mockApi(page);
  });

  test("wizard page loads with Step 1 visible", async ({ page }) => {
    await page.goto("/tests/new");
    await expect(page.getByText(/setup/i)).toBeVisible();
    await expect(page.getByLabel(/test name/i)).toBeVisible();
  });

  test("Step 1: requires test name before advancing", async ({ page }) => {
    await page.goto("/tests/new");
    // Click Next without filling in the name
    await page.getByRole("button", { name: /next/i }).click();
    // Should still be on Step 1
    await expect(page.getByLabel(/test name/i)).toBeVisible();
  });

  test("Step 1 → Step 2: fills required fields and advances", async ({ page }) => {
    await page.goto("/tests/new");

    await page.getByLabel(/test name/i).fill("My CTV Test");

    // Select channel if present (select element)
    const channelSelect = page.locator("select").first();
    if (await channelSelect.isVisible()) {
      await channelSelect.selectOption("ctv");
    }

    await page.getByRole("button", { name: /next/i }).click();

    // Step 2 should show date inputs
    await expect(page.getByText(/dates/i)).toBeVisible();
  });

  test("full wizard: completes all steps and submits", async ({ page }) => {
    await page.goto("/tests/new");

    // Step 1 — config
    await page.getByLabel(/test name/i).fill("Summer CTV Test");
    await page.getByRole("button", { name: /next/i }).click();

    // Step 2 — dates (optional fields, just advance)
    await expect(page.getByText(/dates/i)).toBeVisible();
    await page.getByRole("button", { name: /next/i }).click();

    // Step 3 — review
    await expect(page.getByText(/review/i)).toBeVisible();
    await expect(page.getByText("Summer CTV Test")).toBeVisible();

    // Submit
    await page.getByRole("button", { name: /create test/i }).click();

    // Should redirect to the new test's detail page
    await expect(page).toHaveURL(new RegExp(`/tests/${MOCK_TEST.id}`), { timeout: 10_000 });
  });

  test("back button returns to previous step", async ({ page }) => {
    await page.goto("/tests/new");

    await page.getByLabel(/test name/i).fill("My Test");
    await page.getByRole("button", { name: /next/i }).click();

    // Now on Step 2 — click Back
    await page.getByRole("button", { name: /back/i }).click();

    // Should be back on Step 1 with the name preserved
    await expect(page.getByLabel(/test name/i)).toBeVisible();
    await expect(page.getByLabel(/test name/i)).toHaveValue("My Test");
  });
});
