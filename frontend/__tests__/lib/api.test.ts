/**
 * Tests for the API client layer.
 *
 * Mocks:
 * - @/lib/supabase/client — returns a mock session with a known access_token
 * - global fetch — intercepted per test
 */

// Mock the Supabase browser client before importing api
jest.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: jest.fn().mockResolvedValue({
        data: { session: { access_token: "mock-jwt-token" } },
      }),
    },
  }),
}));

import { api, ApiError } from "@/lib/api";

const mockFetch = jest.fn();
global.fetch = mockFetch;

function mockOkResponse<T>(body: T, status = 200) {
  mockFetch.mockResolvedValueOnce({
    ok: true,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  });
}

function mockErrorResponse(status: number, body = "Error") {
  mockFetch.mockResolvedValueOnce({
    ok: false,
    status,
    statusText: body,
    text: async () => body,
  });
}

beforeEach(() => {
  mockFetch.mockClear();
});

// ---------------------------------------------------------------------------
// Auth headers
// ---------------------------------------------------------------------------

describe("auth headers", () => {
  it("sends Bearer token from Supabase session", async () => {
    mockOkResponse({ items: [], total: 0, page: 1, page_size: 50 });
    await api.tests.list();
    const [, init] = mockFetch.mock.calls[0];
    expect(init.headers.Authorization).toBe("Bearer mock-jwt-token");
  });

  it("sends Content-Type: application/json", async () => {
    mockOkResponse({ items: [], total: 0, page: 1, page_size: 50 });
    await api.tests.list();
    const [, init] = mockFetch.mock.calls[0];
    expect(init.headers["Content-Type"]).toBe("application/json");
  });
});

// ---------------------------------------------------------------------------
// Error handling
// ---------------------------------------------------------------------------

describe("ApiError", () => {
  it("throws ApiError with status code on non-ok response", async () => {
    mockErrorResponse(403, "Forbidden");
    await expect(api.tests.list()).rejects.toBeInstanceOf(ApiError);
  });

  it("ApiError carries the status code", async () => {
    mockErrorResponse(404, "Not found");
    try {
      await api.tests.get("missing-id");
    } catch (e) {
      expect((e as ApiError).status).toBe(404);
    }
  });
});

// ---------------------------------------------------------------------------
// tests namespace
// ---------------------------------------------------------------------------

describe("api.tests.list", () => {
  it("calls GET /api/tests/", async () => {
    mockOkResponse({ items: [], total: 0, page: 1, page_size: 50 });
    await api.tests.list();
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/tests/"),
      expect.objectContaining({ headers: expect.any(Object) })
    );
  });

  it("appends page and page_size query params", async () => {
    mockOkResponse({ items: [], total: 0, page: 2, page_size: 10 });
    await api.tests.list({ page: 2, page_size: 10 });
    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain("page=2");
    expect(url).toContain("page_size=10");
  });

  it("appends status query param when provided", async () => {
    mockOkResponse({ items: [], total: 0, page: 1, page_size: 50 });
    await api.tests.list({ status: "active" });
    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain("status=active");
  });
});

describe("api.tests.get", () => {
  it("calls GET /api/tests/:id", async () => {
    mockOkResponse({ id: "abc", name: "Test" });
    await api.tests.get("abc");
    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/tests/abc");
  });
});

describe("api.tests.create", () => {
  it("calls POST /api/tests/ with body", async () => {
    mockOkResponse({ id: "new", name: "New Test" });
    await api.tests.create({ name: "New Test" });
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/tests/");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toMatchObject({ name: "New Test" });
  });
});

describe("api.tests.update", () => {
  it("calls PATCH /api/tests/:id with body", async () => {
    mockOkResponse({ id: "abc", name: "Updated" });
    await api.tests.update("abc", { name: "Updated" });
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/tests/abc");
    expect(init.method).toBe("PATCH");
  });
});

describe("api.tests.delete", () => {
  it("calls DELETE /api/tests/:id", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, status: 204 });
    await api.tests.delete("abc");
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/tests/abc");
    expect(init.method).toBe("DELETE");
  });
});

// ---------------------------------------------------------------------------
// analysis namespace
// ---------------------------------------------------------------------------

describe("api.analysis.trigger", () => {
  it("calls POST /api/tests/:id/analysis/run", async () => {
    mockOkResponse({ job_id: "job-1", test_id: "t-1", status: "pending", message: "" });
    await api.analysis.trigger("t-1", { spend: 50000 });
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/tests/t-1/analysis/run");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toMatchObject({ spend: 50000 });
  });
});

describe("api.analysis.getLatest", () => {
  it("calls GET /api/tests/:id/analysis/latest", async () => {
    mockOkResponse({ job_id: "j-1", test_id: "t-1", status: "completed" });
    await api.analysis.getLatest("t-1");
    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/tests/t-1/analysis/latest");
  });
});

// ---------------------------------------------------------------------------
// narrative namespace
// ---------------------------------------------------------------------------

describe("api.narrative.generate", () => {
  it("calls POST /api/tests/:id/narrative", async () => {
    mockOkResponse({
      test_id: "t-1",
      job_id: "j-1",
      headline: "Lift confirmed.",
      body_markdown: "## Headline\nLift confirmed.",
      model: "anthropic/claude-sonnet-4-5",
      prompt_tokens: 100,
      completion_tokens: 200,
    });
    await api.narrative.generate("t-1");
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/tests/t-1/narrative");
    expect(init.method).toBe("POST");
  });

  it("includes job_id in body when provided", async () => {
    mockOkResponse({ test_id: "t-1", job_id: "j-99" });
    await api.narrative.generate("t-1", "j-99");
    const [, init] = mockFetch.mock.calls[0];
    expect(JSON.parse(init.body)).toMatchObject({ job_id: "j-99" });
  });
});
