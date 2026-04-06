"""Pydantic schemas for the narrative generation endpoint."""
from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel, Field


class NarrativeRequest(BaseModel):
    """Optional overrides — if omitted, the latest completed result is used."""
    job_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Specific job to narrate. Defaults to the most recent completed job.",
    )
    force_refresh: bool = Field(
        default=False,
        description="Re-generate the narrative even if a cached version exists.",
    )


class NarrativeResponse(BaseModel):
    test_id: uuid.UUID
    job_id: uuid.UUID
    headline: str
    body_markdown: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cached: bool = False
