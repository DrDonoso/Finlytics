"""Add source_path column to import_runs.

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-13

ADDITIVE ONLY — adds a nullable String(500) column for the relative path of
the original uploaded PDF on disk.
* import_runs.source_path — nullable; relative filename under upload_dir.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "import_runs",
        sa.Column("source_path", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("import_runs", "source_path")
