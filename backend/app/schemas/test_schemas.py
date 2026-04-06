"""Pydantic request/response schemas for the tests resource."""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class TestCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    test_type: str = Field(default="geo_split", pattern="^(geo_split|pre_post)$")
    channel: Optional[str] = None
    region_granularity: str = Field(default="state", pattern="^(state|dma|zip)$")
    primary_metric: str = Field(default="revenue", min_length=1)
    n_cells: int = Field(default=2, ge=2, le=4)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    cooldown_weeks: Optional[int] = Field(default=None, ge=0)


class TestUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    channel: Optional[str] = None
    status: Optional[str] = Field(default=None, pattern="^(draft|active|completed)$")
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    cooldown_weeks: Optional[int] = Field(default=None, ge=0)


class TestResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: Optional[str]
    test_type: str
    status: str
    channel: Optional[str]
    region_granularity: str
    primary_metric: str
    n_cells: int
    start_date: Optional[date]
    end_date: Optional[date]

    model_config = {"from_attributes": True}


class TestListResponse(BaseModel):
    items: list[TestResponse]
    total: int
    page: int
    page_size: int
