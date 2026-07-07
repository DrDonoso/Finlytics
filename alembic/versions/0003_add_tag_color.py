"""Add color column to tags table.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-06 13:16:00.000000

This migration is PURELY ADDITIVE — it adds one new NOT NULL column to the
existing ``tags`` table with a server_default so every existing row gets a
sensible fallback colour immediately.  No data is destroyed.  Safe to apply
on a live DB that already has tags and transaction_tags data from revision 0002.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tags",
        sa.Column(
            "color",
            sa.String(length=7),
            nullable=False,
            server_default="#64748b",
        ),
    )


def downgrade() -> None:
    op.drop_column("tags", "color")
