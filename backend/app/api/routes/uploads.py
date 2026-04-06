"""
/api/tests/{test_id}/uploads — CSV upload management.

POST /api/tests/{test_id}/uploads
    Accepts a multipart CSV file, runs column mapping + validation,
    persists a CsvUpload record, and returns structured validation feedback.
    Errors in the CSV block the upload; warnings are returned alongside the
    created record so the UI can surface them without blocking the user.

GET /api/tests/{test_id}/uploads
    Lists all uploads for a test (most recent first).

DELETE /api/tests/{test_id}/uploads/{upload_id}
    Removes an upload record (does not affect already-triggered jobs).
"""
from __future__ import annotations

import io
import uuid
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser
from app.db.session import get_db
from app.models.workspace import CsvUpload, Test
from app.schemas.upload_schemas import CsvUploadResponse, UploadListResponse
from app.services.ingestion.column_mapping import apply_mapping, resolve_column_mapping
from app.services.ingestion.csv_validation import validate_upload

router = APIRouter(prefix="/api/tests/{test_id}/uploads", tags=["uploads"])

_ALLOWED_CONTENT_TYPES = {
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
    "text/plain",       # some browsers send CSV as text/plain
    "application/octet-stream",
}
_MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


# ---------------------------------------------------------------------------
# POST — upload a CSV file
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=CsvUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_csv(
    test_id: uuid.UUID,
    file: UploadFile,
    auth: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    upload_type: str = "historical",
    column_overrides: str = "",  # JSON-encoded {"original": "canonical"} map
) -> CsvUploadResponse:
    """
    Upload a CSV and run validation.

    - **upload_type**: `historical` (baseline) or `results` (post-test).
    - **column_overrides**: optional JSON string mapping original column names
      to canonical names (region, period, metric, spend, prior_metric).

    Returns the created upload record including any validation warnings.
    Raises 422 if the CSV contains hard errors (missing required columns, etc.).
    """
    test = await _get_test_or_403(test_id, auth, db)

    # ── Validate upload_type ────────────────────────────────────────────────
    if upload_type not in ("historical", "results"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="upload_type must be 'historical' or 'results'.",
        )

    # ── Validate file presence and extension ────────────────────────────────
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No file provided.",
        )
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only .csv files are accepted.",
        )

    # ── Read file bytes (size-limited) ──────────────────────────────────────
    raw = await file.read(_MAX_FILE_SIZE_BYTES + 1)
    if len(raw) > _MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File exceeds the 50 MB size limit.",
        )

    # ── Parse CSV ───────────────────────────────────────────────────────────
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not parse CSV: {exc}",
        ) from exc

    # ── Column mapping ──────────────────────────────────────────────────────
    overrides: dict[str, str] = {}
    if column_overrides:
        import json
        try:
            overrides = json.loads(column_overrides)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="column_overrides must be valid JSON.",
            )

    mapping_result = resolve_column_mapping(df.columns.tolist(), overrides or None)
    if not mapping_result.is_complete:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Could not resolve required column names. "
                           "Use column_overrides to map them manually.",
                "missing_columns": mapping_result.missing_canonical,
                "errors": mapping_result.errors,
            },
        )

    df_mapped = apply_mapping(df, mapping_result.mapping)

    # ── Content validation ──────────────────────────────────────────────────
    validation = validate_upload(df_mapped)
    if not validation.is_valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "CSV validation failed.",
                "errors": validation.errors,
                "warnings": validation.warnings,
            },
        )

    # ── Persist upload record ───────────────────────────────────────────────
    storage_path = (
        f"workspaces/{test.workspace_id}/tests/{test_id}/"
        f"{upload_type}/{file.filename}"
    )

    upload = CsvUpload(
        test_id=test_id,
        workspace_id=test.workspace_id,
        upload_type=upload_type,
        storage_path=storage_path,
        filename=file.filename,
        row_count=validation.row_count,
        geo_count=validation.geo_count,
        period_count=validation.period_count,
        column_mapping=mapping_result.mapping,
        validation_warnings=validation.warnings or None,
        data_json=df_mapped.to_json(orient="records"),
        uploaded_by=auth.user_id,
    )
    db.add(upload)
    await db.commit()
    await db.refresh(upload)

    return CsvUploadResponse(
        id=upload.id,
        test_id=upload.test_id,
        workspace_id=upload.workspace_id,
        upload_type=upload.upload_type,
        filename=upload.filename,
        storage_path=upload.storage_path,
        row_count=upload.row_count,
        geo_count=upload.geo_count,
        period_count=upload.period_count,
        column_mapping=upload.column_mapping,
        validation_warnings=upload.validation_warnings,
        uploaded_at=upload.uploaded_at,
    )


# ---------------------------------------------------------------------------
# GET — list uploads
# ---------------------------------------------------------------------------


@router.get("", response_model=UploadListResponse)
async def list_uploads(
    test_id: uuid.UUID,
    auth: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UploadListResponse:
    """List all uploads for a test, most recent first."""
    await _get_test_or_403(test_id, auth, db)

    result = await db.execute(
        select(CsvUpload)
        .where(CsvUpload.test_id == test_id)
        .order_by(CsvUpload.uploaded_at.desc())
    )
    uploads = result.scalars().all()

    return UploadListResponse(
        items=[
            CsvUploadResponse(
                id=u.id,
                test_id=u.test_id,
                workspace_id=u.workspace_id,
                upload_type=u.upload_type,
                filename=u.filename,
                storage_path=u.storage_path,
                row_count=u.row_count,
                geo_count=u.geo_count,
                period_count=u.period_count,
                column_mapping=u.column_mapping,
                validation_warnings=u.validation_warnings,
                uploaded_at=u.uploaded_at,
            )
            for u in uploads
        ],
        total=len(uploads),
    )


# ---------------------------------------------------------------------------
# DELETE — remove an upload record
# ---------------------------------------------------------------------------


@router.delete("/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_upload(
    test_id: uuid.UUID,
    upload_id: uuid.UUID,
    auth: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete an upload record."""
    await _get_test_or_403(test_id, auth, db)

    result = await db.execute(
        select(CsvUpload).where(
            CsvUpload.id == upload_id,
            CsvUpload.test_id == test_id,
        )
    )
    upload = result.scalar_one_or_none()
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found.")

    await db.delete(upload)
    await db.commit()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


async def _get_test_or_403(
    test_id: uuid.UUID, auth: CurrentUser, db: AsyncSession
) -> Test:
    result = await db.execute(select(Test).where(Test.id == test_id))
    test = result.scalar_one_or_none()
    if test is None:
        raise HTTPException(status_code=404, detail="Test not found.")
    if not auth.is_super_admin and test.workspace_id != auth.workspace_id:
        raise HTTPException(status_code=403, detail="Access denied.")
    return test
