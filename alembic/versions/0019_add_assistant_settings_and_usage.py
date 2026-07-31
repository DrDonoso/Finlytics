"""Add assistant_settings and per-message token usage.

Revision ID: 0019
Revises: 0018
Create Date: 2026-07-31

Two related additions behind the assistant Settings page:

* ``assistant_settings`` — per-user overrides for the custom instructions, the
  message rate limit and a monthly token budget. Every column is nullable and
  means "use the environment default", so saving one field does not freeze the
  rest of today's ``ASSISTANT_*`` values into the database.

* token counts on ``assistant_messages`` — needed to show what the assistant
  costs, and to enforce the monthly budget. Counting in the database rather
  than in memory is the point: the in-process rate limiter resets on every
  restart, so it can throttle a burst but can never cap a month's spend.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assistant_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("custom_instructions", sa.Text(), nullable=True),
        sa.Column("rate_limit_messages", sa.Integer(), nullable=True),
        sa.Column("rate_limit_window_seconds", sa.Integer(), nullable=True),
        sa.Column("monthly_token_budget", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_assistant_settings_user"),
    )

    op.add_column(
        "assistant_messages", sa.Column("prompt_tokens", sa.Integer(), nullable=True)
    )
    op.add_column(
        "assistant_messages", sa.Column("completion_tokens", sa.Integer(), nullable=True)
    )
    op.add_column(
        "assistant_messages", sa.Column("total_tokens", sa.Integer(), nullable=True)
    )
    # The budget query sums tokens for one user over a date range every time a
    # turn starts, so it must not table-scan the whole message history.
    op.create_index(
        "ix_assistant_messages_created_at",
        "assistant_messages",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_assistant_messages_created_at", table_name="assistant_messages")
    op.drop_column("assistant_messages", "total_tokens")
    op.drop_column("assistant_messages", "completion_tokens")
    op.drop_column("assistant_messages", "prompt_tokens")
    op.drop_table("assistant_settings")
