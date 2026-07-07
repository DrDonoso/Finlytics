"""Add name_es (Spanish name) column to categories.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-07

ADDITIVE ONLY — adds a single nullable column.  No existing data is modified;
the 33 real transactions and all category rows are fully preserved.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "categories",
        sa.Column("name_es", sa.String(100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("categories", "name_es")
