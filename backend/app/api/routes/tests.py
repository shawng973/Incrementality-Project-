"""
/api/tests — CRUD endpoints for incrementality tests.

All endpoints require authentication. Workspace isolation is enforced in the
query layer (workspace_id filter) — not solely relying on DB RLS, as defense-in-depth.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser
from app.db.session import get_db
from app.models.workspace import Test, TestStatus, TestType, RegionGranularity
from app.schemas.test_schemas import (
    TestCreate,
    TestListResponse,
    TestResponse,
    TestUpdate,
)

router = APIRouter(prefix="/api/tests", tags=["tests"])


@router.get("/", response_model=TestListResponse)
async def list_tests(
    auth: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
) -> TestListResponse:
    """List all tests in the authenticated workspace."""
    workspace_id = auth.workspace_id

    query = select(Test).where(Test.workspace_id == workspace_id)
    if status:
        query = query.where(Test.status == status)

    # Total count
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    # Paginated results
    query = query.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(query)).scalars().all()

    return TestListResponse(
        items=[TestResponse.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/", response_model=TestResponse, status_code=status.HTTP_201_CREATED)
async def create_test(
    auth: CurrentUser,
    body: TestCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TestResponse:
    """Create a new test in the authenticated workspace."""
    test = Test(
        workspace_id=auth.workspace_id,
        created_by=auth.user_id,
        name=body.name,
        description=body.description,
        test_type=TestType(body.test_type),
        channel=body.channel,
        region_granularity=RegionGranularity(body.region_granularity),
        primary_metric=body.primary_metric,
        n_cells=body.n_cells,
        start_date=body.start_date,
        end_date=body.end_date,
        cooldown_weeks=body.cooldown_weeks,
    )
    db.add(test)
    await db.commit()
    await db.refresh(test)
    return TestResponse.model_validate(test)


@router.get("/{test_id}", response_model=TestResponse)
async def get_test(
    test_id: uuid.UUID,
    auth: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TestResponse:
    """Retrieve a single test. Returns 403 if test belongs to another workspace."""
    test = await _get_test_or_raise(test_id, auth.workspace_id, db, auth.is_super_admin)
    return TestResponse.model_validate(test)


@router.patch("/{test_id}", response_model=TestResponse)
async def update_test(
    test_id: uuid.UUID,
    body: TestUpdate,
    auth: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TestResponse:
    """Update a test. Only the owning workspace can modify it."""
    test = await _get_test_or_raise(test_id, auth.workspace_id, db, auth.is_super_admin)

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(test, field, value)

    await db.commit()
    await db.refresh(test)
    return TestResponse.model_validate(test)


@router.delete("/{test_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_test(
    test_id: uuid.UUID,
    auth: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a test. Only the owning workspace can delete it."""
    test = await _get_test_or_raise(test_id, auth.workspace_id, db, auth.is_super_admin)
    await db.delete(test)
    await db.commit()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _get_test_or_raise(
    test_id: uuid.UUID,
    workspace_id: uuid.UUID | None,
    db: AsyncSession,
    is_super_admin: bool,
) -> Test:
    """Fetch test by ID; raise 404 if not found, 403 if wrong workspace."""
    result = await db.execute(select(Test).where(Test.id == test_id))
    test = result.scalar_one_or_none()

    if test is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test not found.")

    if not is_super_admin and test.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this test.",
        )

    return test
