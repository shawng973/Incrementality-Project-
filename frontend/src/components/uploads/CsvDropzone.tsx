"use client";

import { useRef, useState, type DragEvent, type ChangeEvent } from "react";
import { clsx } from "clsx";
import { UploadCloud, FileText, X } from "lucide-react";

interface CsvDropzoneProps {
  onFileSelected: (file: File) => void;
  disabled?: boolean;
  /** Currently selected (but not yet uploaded) file. */
  selectedFile?: File | null;
  onClear?: () => void;
}

export function CsvDropzone({
  onFileSelected,
  disabled = false,
  selectedFile,
  onClear,
}: CsvDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragging(false);
    if (disabled) return;
    const file = e.dataTransfer.files[0];
    if (file) acceptFile(file);
  }

  function handleChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) acceptFile(file);
    // Reset input value so re-selecting same file triggers onChange again
    e.target.value = "";
  }

  function acceptFile(file: File) {
    if (!file.name.toLowerCase().endsWith(".csv")) {
      return; // non-CSV silently ignored — outer component can validate further
    }
    onFileSelected(file);
  }

  if (selectedFile) {
    return (
      <div className="flex items-center gap-3 rounded-lg border border-brand-200 bg-brand-50 px-4 py-3">
        <FileText className="h-5 w-5 flex-shrink-0 text-brand-500" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-brand-900">
            {selectedFile.name}
          </p>
          <p className="text-xs text-brand-500">
            {(selectedFile.size / 1024).toFixed(0)} KB
          </p>
        </div>
        {onClear && (
          <button
            type="button"
            onClick={onClear}
            disabled={disabled}
            aria-label="Remove selected file"
            className="rounded p-1 text-brand-400 hover:text-brand-600 disabled:opacity-50"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
    );
  }

  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-label="CSV drop zone"
      aria-disabled={disabled}
      onDragOver={(e) => { e.preventDefault(); if (!disabled) setIsDragging(true); }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={handleDrop}
      onClick={() => !disabled && inputRef.current?.click()}
      onKeyDown={(e) => e.key === "Enter" && !disabled && inputRef.current?.click()}
      className={clsx(
        "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors",
        isDragging
          ? "border-brand-400 bg-brand-50"
          : "border-gray-300 bg-white hover:border-brand-300 hover:bg-gray-50",
        disabled && "cursor-not-allowed opacity-50"
      )}
    >
      <UploadCloud
        className={clsx(
          "h-8 w-8",
          isDragging ? "text-brand-500" : "text-gray-400"
        )}
      />
      <div>
        <p className="text-sm font-medium text-gray-700">
          Drop a CSV file here, or{" "}
          <span className="text-brand-600 underline">browse</span>
        </p>
        <p className="mt-0.5 text-xs text-gray-400">
          .csv only · max 50 MB
        </p>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept=".csv,text/csv"
        className="sr-only"
        onChange={handleChange}
        disabled={disabled}
        aria-hidden="true"
        data-testid="csv-file-input"
      />
    </div>
  );
}
