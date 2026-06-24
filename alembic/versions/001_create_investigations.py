"""create investigations table

Revision ID: 001_create_investigations
Revises:
Create Date: 2026-06-24
"""

# Alembic's ``op`` object exposes migration helpers at runtime via a dynamic proxy.
# pylint: disable=no-member

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001_create_investigations"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "investigations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("service", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("block_reason", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("state_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("channel_id", sa.String(length=64), server_default="", nullable=False),
        sa.Column("message_ts", sa.String(length=32), server_default="", nullable=False),
        sa.Column("approval_status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("jira_issue_key", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("investigations")
