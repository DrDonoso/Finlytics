"""Add revocable sessions: users.token_version and revoked_tokens.

Revision ID: 0023
Revises: 0022
Create Date: 2026-09-26

A session was a bare signed JWT, valid until it expired: logout only deleted the
cookie, so a copied token kept working for up to 30 days, and there was no way to
end sessions on other devices, not even by changing the password.

``token_version`` is stamped into every token; bumping it ends all sessions at
once. ``revoked_tokens`` lists individual tokens ended by logout, and only needs
to hold each row until that token would have expired anyway.

Tokens issued before this migration carry neither claim and are refused, so every
user signs in once more after the upgrade.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "revoked_tokens",
        sa.Column("jti", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("jti"),
    )


def downgrade() -> None:
    op.drop_table("revoked_tokens")
    op.drop_column("users", "token_version")
