"""Add a per-user system prompt override.

Revision ID: 0020
Revises: 0019
Create Date: 2026-07-31

Lets the owner of a self-hosted instance rewrite the assistant's system prompt
from Settings. Null means "use the shipped default", so clearing the box
restores it rather than sending an empty system message.

Text rather than a bounded String: the shipped prompt is already ~4 KB and the
point of the field is that it can be rewritten freely.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "assistant_settings", sa.Column("system_prompt", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("assistant_settings", "system_prompt")
