"""Add rules table.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-07

ADDITIVE ONLY — creates the rules table; no existing tables are modified.
add_tags uses sa.JSON (not ARRAY) for portability across DB backends.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rules",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("priority", sa.Integer, nullable=False, server_default="100"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        # Match criteria
        sa.Column("description_mode", sa.String(20), nullable=False),
        sa.Column("description_value", sa.Text, nullable=False),
        sa.Column("amount_sign", sa.String(10), nullable=True),
        sa.Column("account_ref", sa.String(100), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        # Actions
        sa.Column("set_category", sa.String(100), nullable=True),
        sa.Column("set_merchant", sa.String(200), nullable=True),
        sa.Column("add_tags", sa.JSON, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("skip_ai", sa.Boolean, nullable=False, server_default="false"),
        # Metadata
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_rules_priority_id", "rules", ["priority", "id"])


def downgrade() -> None:
    op.drop_index("ix_rules_priority_id", table_name="rules")
    op.drop_table("rules")
