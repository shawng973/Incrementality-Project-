/**
 * Typed API client for the FastAPI backend.
 *
 * All methods attach the current Supabase session JWT as a Bearer token.
 * The base URL is read from NEXT_PUBLIC_API_URL (default: localhost:8000).
 */
import { createClient } from "./supabase/client";
import type {
  AnalysisJob,
  AnalysisResult,
  CsvUpload,
  NarrativeResponse,
  PaginatedResponse,
  Test,
  UploadListResponse,
} from "@/types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// Error type
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// ---------------------------------------------------------------------------
// Internal fetch helper
// ---------------------------------------------------------------------------

async function getAuthHeaders(): Promise<HeadersInit> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session) throw new ApiError(401, "Not authenticated");
  return {
    Authorization: `Bearer ${session.access_token}`,
    "Content-Type": "application/json",
  };
}

async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const authHeaders = await getAuthHeaders();
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { ...authHeaders, ...init.headers },
  });

  if (!res.ok) {
    const body = await res.text().catch(() => res.statusText);
    throw new ApiError(res.status, body);
  }

  if (res.status === 204) return undefined as unknown as T;
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Endpoint namespaces
// ---------------------------------------------------------------------------

export const api = {
  tests: {
    list(params?: { page?: number; page_size?: number; status?: string }) {
      const qs = new URLSearchParams();
      if (params?.page) qs.set("page", String(params.page));
      if (params?.page_size) qs.set("page_size", String(params.page_size));
      if (params?.status) qs.set("status", params.status);
      return apiFetch<PaginatedResponse<Test>>(`/api/tests/?${qs}`);
    },

    get(id: string) {
      return apiFetch<Test>(`/api/tests/${id}`);
    },

    create(body: Pick<Test, "name"> & Partial<Omit<Test, "name">>) {
      return apiFetch<Test>("/api/tests/", {
        method: "POST",
        body: JSON.stringify(body),
      });
    },

    update(id: string, body: Partial<Test>) {
      return apiFetch<Test>(`/api/tests/${id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
    },

    delete(id: string) {
      return apiFetch<void>(`/api/tests/${id}`, { method: "DELETE" });
    },
  },

  analysis: {
    trigger(
      testId: string,
      body: { spend: number; has_prior_year?: boolean; n_bootstrap_resamples?: number }
    ) {
      return apiFetch<AnalysisJob>(`/api/tests/${testId}/analysis/run`, {
        method: "POST",
        body: JSON.stringify(body),
      });
    },

    getJob(testId: string, jobId: string) {
      return apiFetch<AnalysisJob>(
        `/api/tests/${testId}/analysis/jobs/${jobId}`
      );
    },

    getLatest(testId: string) {
      return apiFetch<AnalysisResult>(`/api/tests/${testId}/analysis/latest`);
    },
  },

  uploads: {
    async upload(
      testId: string,
      file: File,
      uploadType: "historical" | "results" = "historical"
    ): Promise<CsvUpload> {
      const authHeaders = await getAuthHeaders();
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(
        `${API_BASE}/api/tests/${testId}/uploads?upload_type=${uploadType}`,
        {
          method: "POST",
          headers: { Authorization: (authHeaders as Record<string, string>).Authorization },
          body: formData,
        }
      );
      if (!res.ok) {
        const body = await res.text().catch(() => res.statusText);
        throw new ApiError(res.status, body);
      }
      return res.json() as Promise<CsvUpload>;
    },

    list(testId: string) {
      return apiFetch<UploadListResponse>(`/api/tests/${testId}/uploads`);
    },

    delete(testId: string, uploadId: string) {
      return apiFetch<void>(`/api/tests/${testId}/uploads/${uploadId}`, {
        method: "DELETE",
      });
    },
  },

  narrative: {
    generate(testId: string, jobId?: string) {
      return apiFetch<NarrativeResponse>(`/api/tests/${testId}/narrative`, {
        method: "POST",
        body: JSON.stringify({ job_id: jobId ?? null }),
      });
    },
  },

  pdf: {
    /** Download the latest analysis PDF. Returns a Blob. */
    async downloadLatest(testId: string): Promise<Blob> {
      const authHeaders = await getAuthHeaders();
      const res = await fetch(
        `${API_BASE}/api/tests/${testId}/analysis/latest/pdf`,
        { headers: authHeaders as Record<string, string> }
      );
      if (!res.ok) {
        const body = await res.text().catch(() => res.statusText);
        throw new ApiError(res.status, body);
      }
      return res.blob();
    },
  },
};
