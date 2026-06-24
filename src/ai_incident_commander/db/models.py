"""SQLAlchemy ORM models for normalized investigation persistence."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

if TYPE_CHECKING:
    pass


class Base(DeclarativeBase):
    """Declarative base for ORM models."""


class InvestigationRow(Base):
    """Parent row for a single incident investigation run."""

    __tablename__ = "investigations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    service: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    block_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel_id: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    message_ts: Mapped[str] = mapped_column(String(32), nullable=False, server_default="")
    approval_status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    jira_issue_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    evidence_snapshot: Mapped["EvidenceSnapshotRow | None"] = relationship(
        back_populates="investigation",
        cascade="all, delete-orphan",
        uselist=False,
    )
    rca_hypothesis: Mapped["RcaHypothesisRow | None"] = relationship(
        back_populates="investigation",
        cascade="all, delete-orphan",
        uselist=False,
    )
    eval_results: Mapped[list["EvalResultRow"]] = relationship(
        back_populates="investigation",
        cascade="all, delete-orphan",
    )
    approval_actions: Mapped[list["ApprovalActionRow"]] = relationship(
        back_populates="investigation",
        cascade="all, delete-orphan",
    )


class EvidenceSnapshotRow(Base):
    """Immutable evidence bundle collected for an investigation."""

    __tablename__ = "evidence_snapshots"

    investigation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("investigations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    bundle_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    investigation: Mapped[InvestigationRow] = relationship(back_populates="evidence_snapshot")


class RcaHypothesisRow(Base):
    """Structured RCA output surfaced for human approval."""

    __tablename__ = "rca_hypotheses"

    investigation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("investigations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    root_cause_candidate: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_commit: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    commit_age_minutes: Mapped[int] = mapped_column(nullable=False, server_default="0")
    affected_service: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")
    prior_incident_match: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    synthesized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    investigation: Mapped[InvestigationRow] = relationship(back_populates="rca_hypothesis")


class EvalResultRow(Base):
    """Per-eval audit row for coverage, grounding, and consistency."""

    __tablename__ = "eval_results"
    __table_args__ = (
        UniqueConstraint("investigation_id", "eval_type", name="uq_eval_results_investigation_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    investigation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("investigations.id", ondelete="CASCADE"),
        nullable=False,
    )
    eval_type: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    passed: Mapped[bool] = mapped_column(nullable=False, server_default="true")
    explanation: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    investigation: Mapped[InvestigationRow] = relationship(back_populates="eval_results")


class ApprovalActionRow(Base):
    """Append-only approval workflow events."""

    __tablename__ = "approval_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    investigation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("investigations.id", ondelete="CASCADE"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_slack_id: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    investigation: Mapped[InvestigationRow] = relationship(back_populates="approval_actions")
