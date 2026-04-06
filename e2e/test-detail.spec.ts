/**
 * E2E: Test detail page — the full critical path.
 *
 * Critical path (all mocked against live backend):
 *  1. Navigate to test detail
 *  2. See results summary (with mocked completed analysis)
 *  3. Expand "Upload data" section and upload a CSV
 *  4. Expand "Run a new analysis" and trigger analysis
 *  5. See job progress spinner
 *  6. See results update after job completes
 *  7. Export PDF button triggers download
 */
import path from "path";
import { test, expect, mockApi, MOCK_TEST, MOCK_TEST_ID, MOCK_ANALYSIS_RESULT } from "./fixtures";

test.describe("Test detail — results already exist", () => {
  test.use({ storageState: "e2e/.auth/user.json" });

  test.beforeEach(async ({ page }) => {
    await mockApi(page);
  });

  test("shows test name and metadata in header", async ({ page }) => {
    await page.goto(`/tests/${MOCK_TEST_ID}`);
    await expect(page.getByRole("heading", { name: MOCK_TEST.name })).toBeVisible();
    await expect(page.getByText(/ctv/i)).toBeVisible();
  });

  test("shows back link to tests list", async ({ page }) => {
    await page.goto(`/tests/${MOCK_TEST_ID}`);
    const backLink = page.getByRole("link", { name: /tests/i });
    await expect(backLink).toBeVisible();
    await backLink.click();
    await expect(page).toHaveURL(/\/tests$/);
  });

  test("results summary card is visible", async ({ page }) => {
    await page.goto(`/tests/${MOCK_TEST_ID}`);
    await expect(page.getByText(/results summary/i)).toBeVisible();
  });

  test("Export PDF button is visible in results summary", async ({ page }) => {
    await page.goto(`/tests/${MOCK_TEST_ID}`);
    await expect(page.getByRole("button", { name: /export pdf/i })).toBeVisible();
  });

  test("Export PDF button triggers a download", async ({ page }) => {
    await page.goto(`/tests/${MOCK_TEST_ID}`);

    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: /export pdf/i }).click(),
    ]);

    expect(download.suggestedFilename()).toMatch(/\.pdf$/);
  });

  test("AI narrative section is visible and expandable", async ({ page }) => {
    await page.goto(`/tests/${MOCK_TEST_ID}`);
    await expect(page.getByText(/ai narrative/i)).toBeVisible();
  });

  test("Statistical detail section can be expanded", async ({ page }) => {
    await page.goto(`/tests/${MOCK_TEST_ID}`);
    await page.getByText(/statistical detail/i).click();
    // After expanding, should show TWFE content
    await expect(page.getByText(/twfe/i)).toBeVisible();
  });

  test("Upload data section can be expanded", async ({ page }) => {
    await page.goto(`/tests/${MOCK_TEST_ID}`);
    await page.getByText(/upload data/i).click();
    await expect(page.getByText(/historical baseline/i)).toBeVisible();
  });
});

test.describe("Test detail — CSV upload flow", () => {
  test.use({ storageState: "e2e/.auth/user.json" });

  test.beforeEach(async ({ page }) => {
    await mockApi(page);
  });

  test("CSV dropzone accepts a .csv file and shows upload button", async ({ page }) => {
    await page.goto(`/tests/${MOCK_TEST_ID}`);
    await page.getByText(/upload data/i).click();

    // Create a dummy CSV buffer
    const csvContent = "region,period,metric\ngeo_1,2024-01,1000\ngeo_2,2024-01,900";
    const fileName = "test_data.csv";

    // Find the hidden file input and set the file
    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles({
      name: fileName,
      mimeType: "text/csv",
      buffer: Buffer.from(csvContent),
    });

    // Upload button should appear
    await expect(page.getByRole("button", { name: /^upload$/i }).first()).toBeVisible();
  });

  test("successful upload shows success stats", async ({ page }) => {
    await page.goto(`/tests/${MOCK_TEST_ID}`);
    await page.getByText(/upload data/i).click();

    const csvContent = "region,period,metric\ngeo_1,2024-01,1000";
    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles({
      name: "data.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(csvContent),
    });

    await page.getByRole("button", { name: /^upload$/i }).first().click();

    // Success stats (row_count / geo_count)
    await expect(page.getByText(/480/)).toBeVisible({ timeout: 8_000 });
  });

  test("non-CSV file is ignored by the dropzone", async ({ page }) => {
    await page.goto(`/tests/${MOCK_TEST_ID}`);
    await page.getByText(/upload data/i).click();

    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles({
      name: "data.xlsx",
      mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      buffer: Buffer.from("fake excel"),
    });

    // Upload button should NOT appear (non-CSV rejected)
    await expect(page.getByRole("button", { name: /^upload$/i })).not.toBeVisible();
  });
});

test.describe("Test detail — run analysis flow", () => {
  test.use({ storageState: "e2e/.auth/user.json" });

  test.beforeEach(async ({ page }) => {
    await mockApi(page);
  });

  test("analysis trigger form requires spend amount", async ({ page }) => {
    await page.goto(`/tests/${MOCK_TEST_ID}`);
    await page.getByText(/run a new analysis/i).click();

    // Click Run without entering spend
    await page.getByRole("button", { name: /run analysis/i }).click();

    // Error message should appear
    await expect(page.getByRole("alert")).toBeVisible();
  });

  test("entering spend and clicking Run shows progress spinner", async ({ page }) => {
    await page.goto(`/tests/${MOCK_TEST_ID}`);
    await page.getByText(/run a new analysis/i).click();

    await page.getByLabel(/total test spend/i).fill("50000");
    await page.getByRole("button", { name: /run analysis/i }).click();

    // Spinner / "in progress" text should appear
    await expect(
      page.getByText(/analysis in progress/i).or(page.getByText(/pending/i))
    ).toBeVisible({ timeout: 8_000 });
  });
});

test.describe("Test detail — no results yet", () => {
  test.use({ storageState: "e2e/.auth/user.json" });

  test("shows 'Run analysis' card when no results exist", async ({ page }) => {
    // Override the analysis/latest mock to return 404
    await page.route("**/api/tests/**/analysis/latest", (route) =>
      route.fulfill({ status: 404, body: "{}" })
    );
    await mockApi(page);

    await page.goto(`/tests/${MOCK_TEST_ID}`);
    await expect(page.getByText(/run analysis/i)).toBeVisible();
    await expect(page.getByText(/no analysis has been run/i)).toBeVisible();
  });
});
