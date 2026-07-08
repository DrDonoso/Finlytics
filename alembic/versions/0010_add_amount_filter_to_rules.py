"""Add amount_min and amount_max filter columns to rules.

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-08

ADDITIVE ONLY — adds two nullable Numeric columns; no existing data is modified.
* rules.amount_min  — lower bound for abs(amount) filter (>=), or NULL = no lower bound
* rules.amount_max  — upper bound for abs(amount) filter (<=), or NULL = no upper bound

Precision and scale match Transaction.amount (Numeric(14, 2)).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "rules",
        sa.Column("amount_min", sa.Numeric(14, 2), nullable=True),
    )
    op.add_column(
        "rules",
        sa.Column("amount_max", sa.Numeric(14, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("rules", "amount_max")
    op.drop_column("rules", "amount_min")
