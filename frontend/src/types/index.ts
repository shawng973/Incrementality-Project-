export type TestStatus = "draft" | "active" | "completed";
export type TestType = "geo_split" | "pre_post";
export type RegionGranularity = "state" | "dma" | "zip";
export type JobStatus = "pending" | "running" | "completed" | "failed";

export interface Test {
  id: string;
  workspace_id: string;
  name: string;
  description?: string;
  test_type: TestType;
  status: TestStatus;
  channel?: string;
  region_granularity: RegionGranularity;
  primary_metric: string;
  start_date?: string;
  end_date?: string;
  n_cells: number;
  created_at: string;
  updated_at: string;
}

export interface AnalysisJob {
  job_id: string;
  test_id: string;
  workspace_id: string;
  status: JobStatus;
  message: string;
}

export interface CIBound {
  lower: number;
  upper: number;
}

export interface AnalysisResult {
  job_id: string;
  test_id: string;
  status: string;
  parallel_trends_passes?: boolean;
  parallel_trends_p_value?: number;
  parallel_trends_flag?: string;
  twfe_treatment_effect?: number;
  twfe_treatment_effect_dollars?: number;
  twfe_p_value?: number;
  twfe_ci_80?: CIBound;
  twfe_ci_90?: CIBound;
  twfe_ci_95?: CIBound;
  simple_did_estimate?: number;
  simple_did_dollars?: number;
  yoy_did_proportion?: number;
  yoy_did_dollars?: number;
  is_causally_clean?: boolean;
  adjusted_yoy_did_dollars?: number;
  incremental_revenue_midpoint?: number;
  incremental_revenue_weighted?: number;
  roas_low?: number;
  roas_mid?: number;
  roas_high?: number;
  roas_ci_95?: CIBound;
  total_spend?: number;
  power_analysis_json?: {
    power: number;
    is_adequately_powered: boolean;
    required_weeks?: number;
    warning_message?: string;
  };
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface CsvUpload {
  id: string;
  test_id: string;
  workspace_id: string;
  upload_type: "historical" | "results";
  filename: string;
  storage_path: string;
  row_count?: number;
  geo_count?: number;
  period_count?: number;
  column_mapping?: Record<string, string>;
  validation_warnings?: string[];
  uploaded_at: string;
}

export interface UploadListResponse {
  items: CsvUpload[];
  total: number;
}

export interface NarrativeResponse {
  test_id: string;
  job_id: string;
  headline: string;
  body_markdown: string;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
}
