/**
 * Shared Playwright fixtures and mock-data helpers.
 *
 * Provides:
 *  - `authenticatedPage` — a Page with the saved Supabase auth storageState
 *    pre-loaded, so tests skip the login form.
 *  - `mockApi` — convenience helper to set up common route intercepts
 *    (backend API mocks) so tests do not need a live backend.
 */
import { test as base, expect, Page } from "@playwright/test";
import { AUTH_FILE } from "./global-setup";

// ---------------------------------------------------------------------------
// Shared mock data
// ---------------------------------------------------------------------------

export const MOCK_TEST_ID = "aaaaaaaa-0000-0000-0000-000000000001";

export const MOCK_TEST = {
  id: MOCK_TEST_ID,
  name: "Summer CTV Test",
  status: "active",
  channel: "ctv",
  region_granularity: "dma",
  n_cells: 2,
  start_date: "2024-06-01",
  end_date: "2024-08-31",
  description: "Holdout test for CTV campaign",
  workspace_id: "ws-001",
  created_at: "2024-05-01T00:00:00Z",
};

export const MOCK_ANALYSIS_RESULT = {
  job_id: "bbbbbbbb-0000-0000-0000-000000000001",
  test_id: MOCK_TEST_ID,
  status: "completed",
  twfe_treatment_effect: 0.14,
  twfe_treatment_effect_dollars: 112_000,
  twfe_p_value: 0.021,
  twfe_ci_95: { lower: 0.06, upper: 0.22 },
  simple_did_estimate: 0.13,
  simple_did_dollars: 104_000,
  incremental_revenue_midpoint: 108_000,
  roas_mid: 2.16,
  roas_low: 1.6,
  roas_high: 2.8,
  total_spend: 50_000,
  parallel_trends_passes: true,
  parallel_trends_p_value: 0.38,
  power_analysis_json: { power: 0.85, is_adequately_powered: true, required_weeks: 6 },
};

export const MOCK_JOB_PENDING = {
  job_id: "cccccccc-0000-0000-0000-000000000001",
  test_id: MOCK_TEST_ID,
  status: "pending",
  message: "",
};

export const MOCK_JOB_COMPLETED = {
  ...MOCK_JOB_PENDING,
  status: "completed",
};

export const MOCK_UPLOAD = {
  id: "dddddddd-0000-0000-0000-000000000001",
  test_id: MOCK_TEST_ID,
  workspace_id: "ws-001",
  upload_type: "historical",
  filename: "baseline_data.csv",
  storage_path: "workspaces/ws-001/tests/test-1/historical/baseline_data.csv",
  row_count: 480,
  geo_count: 60,
  period_count: 8,
  validation_warnings: [],
  uploaded_at: "2024-05-10T12:00:00Z",
};

// ---------------------------------------------------------------------------
// Route mock helper
// ---------------------------------------------------------------------------

export async function mockApi(page: Page) {
  const base = "http://localhost:8000";

  // Tests list
  await page.route(`${base}/api/tests/**`, async (route) => {
    const url = route.request().url();
    const method = route.request().method();

    // POST /api/tests/ — create
    if (method === "POST" && url.endsWith("/api/tests/")) {
      return route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(MOCK_TEST),
      });
    }

    // GET /api/tests/{id}/analysis/latest/pdf
    if (url.includes("/analysis/latest/pdf")) {
      return route.fulfill({
        status: 200,
        contentType: "application/pdf",
        body: "%PDF-1.4 fake",
      });
    }

    // GET /api/tests/{id}/analysis/latest
    if (url.includes("/analysis/latest")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_ANALYSIS_RESULT),
      });
    }

    // GET /api/tests/{id}/analysis/jobs/{jobId}
    if (url.includes("/analysis/jobs/")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_JOB_COMPLETED),
      });
    }

    // POST /api/tests/{id}/analysis/run
    if (url.includes("/analysis/run")) {
      return route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify(MOCK_JOB_PENDING),
      });
    }

    // POST /api/tests/{id}/uploads
    if (url.includes("/uploads") && method === "POST") {
      return route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(MOCK_UPLOAD),
      });
    }

    // GET /api/tests/{id}/uploads
    if (url.includes("/uploads") && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [MOCK_UPLOAD], total: 1 }),
      });
    }

    // POST /api/tests/{id}/narrative
    if (url.includes("/narrative")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          job_id: MOCK_JOB_COMPLETED.job_id,
          headline: "Strong incremental lift detected",
          body: "The test showed a statistically significant lift of 14% with ROAS of 2.16x.",
          generated_at: "2024-09-01T00:00:00Z",
        }),
      });
    }

    // GET /api/tests/{id}
    if (url.match(/\/api\/tests\/[^/]+$/) && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_TEST),
      });
    }

    // GET /api/tests/ — list
    if (url.includes("/api/tests/") && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [MOCK_TEST],
          total: 1,
          page: 1,
          page_size: 20,
        }),
      });
    }

    return route.fallback();
  });
}

// ---------------------------------------------------------------------------
// Extended test fixture
// ---------------------------------------------------------------------------

type Fixtures = {
  authedPage: Page;
};

export const test = base.extend<Fixtures>({
  authedPage: async ({ browser }, use) => {
    const context = await browser.newContext({ storageState: AUTH_FILE });
    const page = await context.newPage();
    await use(page);
    await context.close();
  },
});

export { expect };
