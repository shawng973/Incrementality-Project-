"""Pydantic schemas for the CSV upload endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class CsvUploadResponse(BaseModel):
    id: uuid.UUID
    test_id: uuid.UUID
    workspace_id: uuid.UUID
    upload_type: str
    filename: str
    storage_path: str
    row_count: Optional[int] = None
    geo_count: Optional[int] = None
    period_count: Optional[int] = None
    column_mapping: Optional[dict[str, Any]] = None
    validation_warnings: Optional[list[str]] = None
    uploaded_at: datetime

    model_config = {"from_attributes": True}


class UploadListResponse(BaseModel):
    items: list[CsvUploadResponse]
    total: int
