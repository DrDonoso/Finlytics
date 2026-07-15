"""Add investment_portfolio_cache table.

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-15

One row per investment_connections.id (UNIQUE on connection_id).
payload (JSON) stores the serialised NormalizedPortfolio so the
/portfolio endpoint returns immediately without a live Indexa API call.
Freshness window: ~24 h; stale rows are served immediately and refreshed
asynchronously via FastAPI BackgroundTasks.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "investment_portfolio_cache",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["investment_connections.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connection_id", name="uq_portfolio_cache_connection_id"),
    )
    op.create_index(
        "ix_portfolio_cache_connection_id",
        "investment_portfolio_cache",
        ["connection_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_portfolio_cache_connection_id", table_name="investment_portfolio_cache")
    op.drop_table("investment_portfolio_cache")
