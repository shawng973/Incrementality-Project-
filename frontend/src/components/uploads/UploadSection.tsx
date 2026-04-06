"use client";

import { useState } from "react";
import { CsvDropzone } from "./CsvDropzone";
import { ValidationWarnings, UploadSuccessStats } from "./ValidationWarnings";
import { Button } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api";
import type { CsvUpload } from "@/types";

interface UploadSectionProps {
  testId: string;
  uploadType?: "historical" | "results";
  /** Called after a successful upload. */
  onUploaded?: (upload: CsvUpload) => void;
}

type UploadState =
  | { status: "idle" }
  | { status: "selected"; file: File }
  | { status: "uploading"; file: File }
  | { status: "success"; upload: CsvUpload }
  | { status: "error"; errors: string[]; warnings: string[] };

export function UploadSection({
  testId,
  uploadType = "historical",
  onUploaded,
}: UploadSectionProps) {
  const [state, setState] = useState<UploadState>({ status: "idle" });

  function handleFileSelected(file: File) {
    setState({ status: "selected", file });
  }

  function handleClear() {
    setState({ status: "idle" });
  }

  async function handleUpload() {
    if (state.status !== "selected") return;
    const { file } = state;
    setState({ status: "uploading", file });

    try {
      const upload = await api.uploads.upload(testId, file, uploadType);
      setState({ status: "success", upload });
      onUploaded?.(upload);
    } catch (err) {
      if (err instanceof ApiError) {
        // Try to parse structured error body
        try {
          const body = JSON.parse(err.message);
          setState({
            status: "error",
            errors: body.errors ?? [body.message ?? err.message],
            warnings: body.warnings ?? [],
          });
        } catch {
          setState({
            status: "error",
            errors: [err.message],
            warnings: [],
          });
        }
      } else {
        setState({
          status: "error",
          errors: ["An unexpected error occurred. Please try again."],
          warnings: [],
        });
      }
    }
  }

  const isUploading = state.status === "uploading";

  return (
    <div className="space-y-4">
      <div>
        <h3 className="mb-1 text-sm font-semibold text-gray-800 capitalize">
          {uploadType === "historical" ? "Historical baseline data" : "Post-test results data"}
        </h3>
        <p className="text-xs text-gray-500">
          {uploadType === "historical"
            ? "Upload your baseline period CSV. Required columns: region, period, metric."
            : "Upload your post-test period CSV with the same structure as the baseline."}
        </p>
      </div>

      <CsvDropzone
        onFileSelected={handleFileSelected}
        disabled={isUploading || state.status === "success"}
        selectedFile={
          state.status === "selected" || state.status === "uploading"
            ? state.file
            : null
        }
        onClear={handleClear}
      />

      {state.status === "error" && (
        <ValidationWarnings
          errors={state.errors}
          warnings={state.warnings}
        />
      )}

      {state.status === "success" && (
        <>
          <UploadSuccessStats
            rowCount={state.upload.row_count}
            geoCount={state.upload.geo_count}
            periodCount={state.upload.period_count}
          />
          {state.upload.validation_warnings &&
            state.upload.validation_warnings.length > 0 && (
              <ValidationWarnings warnings={state.upload.validation_warnings} />
            )}
        </>
      )}

      {(state.status === "selected" || state.status === "uploading") && (
        <div className="flex justify-end">
          <Button
            onClick={handleUpload}
            isLoading={isUploading}
            size="sm"
          >
            Upload
          </Button>
        </div>
      )}

      {state.status === "error" && (
        <div className="flex justify-end">
          <Button variant="secondary" size="sm" onClick={handleClear}>
            Try a different file
          </Button>
        </div>
      )}

      {state.status === "success" && (
        <div className="flex justify-end">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setState({ status: "idle" })}
          >
            Upload another file
          </Button>
        </div>
      )}
    </div>
  );
}
