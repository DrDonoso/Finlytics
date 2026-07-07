"""Add merchant column to transactions.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-07

ADDITIVE ONLY — adds a single nullable VARCHAR column.  No existing data is
modified; the 33 real transactions get merchant = NULL automatically.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("merchant", sa.String(200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("transactions", "merchant")
