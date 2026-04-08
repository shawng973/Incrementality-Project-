"""SQLAlchemy ORM models — mirrors 001_initial_schema.sql."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class TestStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"


class TestType(str, enum.Enum):
    GEO_SPLIT = "geo_split"
    PRE_POST = "pre_post"


class RegionGranularity(str, enum.Enum):
    STATE = "state"
    DMA = "dma"
    ZIP = "zip"


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    PRACTITIONER = "practitioner"
    C_SUITE = "c_suite"


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    users: Mapped[list[WorkspaceUser]] = relationship(
        "WorkspaceUser", back_populates="workspace"
    )
    tests: Mapped[list[Test]] = relationship("Test", back_populates="workspace")


class WorkspaceUser(Base):
    __tablename__ = "workspace_users"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, values_callable=lambda x: [e.value for e in x]), nullable=False, default=UserRole.PRACTITIONER
    )
    invited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    workspace: Mapped[Workspace] = relationship("Workspace", back_populates="users")


class Test(Base):
    __tablename__ = "tests"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    test_type: Mapped[TestType] = mapped_column(
        Enum(TestType, values_callable=lambda x: [e.value for e in x]), nullable=False, default=TestType.GEO_SPLIT
    )
    status: Mapped[TestStatus] = mapped_column(
        Enum(TestStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=TestStatus.DRAFT
    )
    channel: Mapped[Optional[str]] = mapped_column(String)
    region_granularity: Mapped[RegionGranularity] = mapped_column(
        Enum(RegionGranularity, values_callable=lambda x: [e.value for e in x]), nullable=False, default=RegionGranularity.STATE
    )
    primary_metric: Mapped[str] = mapped_column(String, nullable=False, default="revenue")
    start_date: Mapped[Optional[datetime]] = mapped_column(Date)
    end_date: Mapped[Optional[datetime]] = mapped_column(Date)
    cooldown_weeks: Mapped[Optional[int]] = mapped_column(Integer)
    n_cells: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    workspace: Mapped[Workspace] = relationship("Workspace", back_populates="tests")
    geo_assignments: Mapped[list[GeoAssignment]] = relationship(
        "GeoAssignment", back_populates="test"
    )
    uploads: Mapped[list[CsvUpload]] = relationship("CsvUpload", back_populates="test")
    jobs: Mapped[list[AnalysisJob]] = relationship("AnalysisJob", back_populates="test")


class GeoAssignment(Base):
    __tablename__ = "geo_assignments"
    __table_args__ = (UniqueConstraint("test_id", "geo"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    test_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tests.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    geo: Mapped[str] = mapped_column(String, nullable=False)
    cell_id: Mapped[int] = mapped_column(Integer, nullable=False)
    cluster_id: Mapped[Optional[int]] = mapped_column(Integer)
    avg_metric: Mapped[Optional[float]] = mapped_column(Float)

    test: Mapped[Test] = relationship("Test", back_populates="geo_assignments")


class CsvUpload(Base):
    __tablename__ = "csv_uploads"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    test_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tests.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    upload_type: Mapped[str] = mapped_column(String, nullable=False)
    storage_path: Mapped[str] = mapped_column(String, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    row_count: Mapped[Optional[int]] = mapped_column(Integer)
    geo_count: Mapped[Optional[int]] = mapped_column(Integer)
    period_count: Mapped[Optional[int]] = mapped_column(Integer)
    column_mapping: Mapped[Optional[dict]] = mapped_column(JSON)
    validation_warnings: Mapped[Optional[list]] = mapped_column(JSON)
    data_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    test: Mapped[Test] = relationship("Test", back_populates="uploads")


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    test_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tests.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=JobStatus.PENDING
    )
    triggered_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    enqueued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    error_detail: Mapped[Optional[dict]] = mapped_column(JSON)

    test: Mapped[Test] = relationship("Test", back_populates="jobs")
    result: Mapped[Optional[AnalysisResult]] = relationship(
        "AnalysisResult", back_populates="job", uselist=False
    )


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("analysis_jobs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    test_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tests.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )

    # Parallel trends
    parallel_trends_passes: Mapped[Optional[bool]] = mapped_column(Boolean)
    parallel_trends_p_value: Mapped[Optional[float]] = mapped_column(Float)
    parallel_trends_flag: Mapped[Optional[str]] = mapped_column(Text)

    # TWFE DiD
    twfe_treatment_effect: Mapped[Optional[float]] = mapped_column(Float)
    twfe_treatment_effect_dollars: Mapped[Optional[float]] = mapped_column(Float)
    twfe_p_value: Mapped[Optional[float]] = mapped_column(Float)
    twfe_ci_80: Mapped[Optional[dict]] = mapped_column(JSON)
    twfe_ci_90: Mapped[Optional[dict]] = mapped_column(JSON)
    twfe_ci_95: Mapped[Optional[dict]] = mapped_column(JSON)
    twfe_se: Mapped[Optional[float]] = mapped_column(Float)

    # Simple DiD
    simple_did_estimate: Mapped[Optional[float]] = mapped_column(Float)
    simple_did_dollars: Mapped[Optional[float]] = mapped_column(Float)

    # YoY
    yoy_did_proportion: Mapped[Optional[float]] = mapped_column(Float)
    yoy_did_dollars: Mapped[Optional[float]] = mapped_column(Float)

    # Pre-trend adjustment
    beta_pre: Mapped[Optional[float]] = mapped_column(Float)
    beta_pre_p_value: Mapped[Optional[float]] = mapped_column(Float)
    adjusted_yoy_did_dollars: Mapped[Optional[float]] = mapped_column(Float)
    is_causally_clean: Mapped[Optional[bool]] = mapped_column(Boolean)

    # Reconciled incrementality
    incremental_revenue_midpoint: Mapped[Optional[float]] = mapped_column(Float)
    incremental_revenue_weighted: Mapped[Optional[float]] = mapped_column(Float)

    # ROAS
    roas_low: Mapped[Optional[float]] = mapped_column(Float)
    roas_mid: Mapped[Optional[float]] = mapped_column(Float)
    roas_high: Mapped[Optional[float]] = mapped_column(Float)
    roas_ci_95: Mapped[Optional[dict]] = mapped_column(JSON)

    total_spend: Mapped[Optional[float]] = mapped_column(Float)

    # Raw blobs
    delta_vs_baseline_json: Mapped[Optional[dict]] = mapped_column(JSON)
    weekly_did_json: Mapped[Optional[dict]] = mapped_column(JSON)
    weekly_yoy_json: Mapped[Optional[dict]] = mapped_column(JSON)
    power_analysis_json: Mapped[Optional[dict]] = mapped_column(JSON)
    cluster_summary_json: Mapped[Optional[dict]] = mapped_column(JSON)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    job: Mapped[AnalysisJob] = relationship("AnalysisJob", back_populates="result")


class NarrativeResult(Base):
    __tablename__ = "narrative_results"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("analysis_jobs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    test_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tests.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    job: Mapped[AnalysisJob] = relationship("AnalysisJob")
