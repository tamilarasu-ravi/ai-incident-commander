"""normalize investigation schema into child tables

Revision ID: 002_normalize_schema
Revises: 001_create_investigations
Create Date: 2026-06-24
"""

# Alembic's ``op`` object exposes migration helpers at runtime via a dynamic proxy.
# pylint: disable=no-member

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from ai_incident_commander.db.migration_helpers import backfill_normalized_children

revision: str = "002_normalize_schema"
down_revision: Union[str, Sequence[str], None] = "001_create_investigations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names(connection) -> set[str]:
    """Return existing table names for idempotent migration steps."""
    inspector = sa.inspect(connection)
    return set(inspector.get_table_names())


def _column_names(connection, table_name: str) -> set[str]:
    """Return column names for a table when it exists."""
    inspector = sa.inspect(connection)
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    connection = op.get_bind()
    tables = _table_names(connection)

    if "evidence_snapshots" not in tables:
        op.create_table(
            "evidence_snapshots",
            sa.Column("investigation_id", sa.String(length=36), nullable=False),
            sa.Column("bundle_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column(
                "collected_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("investigation_id"),
        )
    if "rca_hypotheses" not in tables:
        op.create_table(
            "rca_hypotheses",
            sa.Column("investigation_id", sa.String(length=36), nullable=False),
            sa.Column("root_cause_candidate", sa.Text(), nullable=False),
            sa.Column("supporting_commit", sa.String(length=64), server_default="", nullable=False),
            sa.Column("commit_age_minutes", sa.Integer(), server_default="0", nullable=False),
            sa.Column("affected_service", sa.String(length=255), server_default="", nullable=False),
            sa.Column("prior_incident_match", sa.String(length=64), server_default="", nullable=False),
            sa.Column("confidence", sa.Float(), server_default="0", nullable=False),
            sa.Column(
                "synthesized_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("investigation_id"),
        )
    if "eval_results" not in tables:
        op.create_table(
            "eval_results",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("investigation_id", sa.String(length=36), nullable=False),
            sa.Column("eval_type", sa.String(length=32), nullable=False),
            sa.Column("score", sa.Float(), nullable=False),
            sa.Column("passed", sa.Boolean(), server_default="true", nullable=False),
            sa.Column("explanation", sa.Text(), server_default="", nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("investigation_id", "eval_type", name="uq_eval_results_investigation_type"),
        )
    if "approval_actions" not in tables:
        op.create_table(
            "approval_actions",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("investigation_id", sa.String(length=36), nullable=False),
            sa.Column("action", sa.String(length=32), nullable=False),
            sa.Column("actor_slack_id", sa.String(length=64), server_default="", nullable=False),
            sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    backfill_normalized_children(connection)

    investigation_columns = _column_names(connection, "investigations")
    if "state_json" in investigation_columns:
        op.drop_column("investigations", "state_json")


def downgrade() -> None:
    op.add_column(
        "investigations",
        sa.Column("state_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.drop_table("approval_actions")
    op.drop_table("eval_results")
    op.drop_table("rca_hypotheses")
    op.drop_table("evidence_snapshots")
