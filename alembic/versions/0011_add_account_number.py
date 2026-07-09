"""Add account_number column to accounts.

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-09

ADDITIVE ONLY — adds a nullable String(34) column for the account IBAN.
* accounts.account_number — nullable; unique per account when non-NULL.
* A partial unique index (WHERE account_number IS NOT NULL) enforces IBAN
  uniqueness explicitly so that multiple NULL values are permitted (one row
  per yet-unnamed account).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("account_number", sa.String(34), nullable=True),
    )
    # Partial unique index: only one row per IBAN; NULLs are not unique.
    op.create_index(
        "ix_accounts_account_number",
        "accounts",
        ["account_number"],
        unique=True,
        postgresql_where=sa.text("account_number IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_accounts_account_number", table_name="accounts")
    op.drop_column("accounts", "account_number")
