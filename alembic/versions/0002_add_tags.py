"""Add tags and transaction_tags tables.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-06 12:22:00.000000

This migration is PURELY ADDITIVE — it creates two new tables and does not
touch any existing table, column, or index.  Safe to apply on a live DB that
already has data from revision 0001.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── tags ──────────────────────────────────────────────────────────────────
    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_tags_name", "tags", ["name"], unique=True)

    # ── transaction_tags (join table) ─────────────────────────────────────────
    # ON DELETE CASCADE on both FKs so:
    #   - Deleting a Transaction removes its tag links automatically.
    #   - Deleting a Tag removes its transaction links automatically.
    op.create_table(
        "transaction_tags",
        sa.Column("transaction_id", sa.BigInteger(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["transaction_id"], ["transactions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"], ["tags.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("transaction_id", "tag_id"),
    )
    op.create_index(
        "ix_transaction_tags_tag_id", "transaction_tags", ["tag_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_transaction_tags_tag_id", table_name="transaction_tags")
    op.drop_table("transaction_tags")
    op.drop_index("ix_tags_name", table_name="tags")
    op.drop_table("tags")
