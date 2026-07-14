"""Add investment_connections table.

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-14

ADDITIVE ONLY — creates the investment_connections table for storing
encrypted Indexa Capital (and future provider) API tokens.

One row per provider account.  token_enc holds Fernet ciphertext only;
plaintext is NEVER stored (Romanoff security policy).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "investment_connections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("plugin_id", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("account_label_masked", sa.String(50), nullable=True),
        sa.Column("token_enc", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_investment_connections_user_id",
        "investment_connections",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_investment_connections_user_id", table_name="investment_connections")
    op.drop_table("investment_connections")
