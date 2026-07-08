"""Add detail fields to transactions and rules.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-08

ADDITIVE ONLY — adds three nullable columns; no existing data is modified.
* transactions.detail      — non-bold sub-line text from the statement
* rules.detail_mode        — match mode for the detail field (mirrors description_mode)
* rules.detail_value       — match value for the detail field

dedup_hash for existing rows is unaffected: detail was absent before, and the
new compute_dedup_hash only appends a detail component when detail is non-empty.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("detail", sa.String(500), nullable=True),
    )
    op.add_column(
        "rules",
        sa.Column("detail_mode", sa.String(20), nullable=True),
    )
    op.add_column(
        "rules",
        sa.Column("detail_value", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("rules", "detail_value")
    op.drop_column("rules", "detail_mode")
    op.drop_column("transactions", "detail")
