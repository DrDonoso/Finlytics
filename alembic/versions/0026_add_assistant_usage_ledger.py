"""Add the assistant usage ledger.

Revision ID: 0026
Revises: 0025
Create Date: 2026-09-28

Token usage used to be read back from ``assistant_messages``. Deleting a
conversation cascades its messages away, so it also handed the tokens they
cost back to the monthly budget: delete the thread, and the spend was never
counted. The ledger is keyed on the user and only loses the conversation link
(SET NULL) when the thread is deleted, so the budget survives it.

The backfill copies every row that carries a turn's cost today: each answer,
plus the question of a turn that spent tokens without answering.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assistant_usage",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            sa.Integer,
            sa.ForeignKey("assistant_conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("prompt_tokens", sa.Integer, nullable=True),
        sa.Column("completion_tokens", sa.Integer, nullable=True),
        sa.Column("total_tokens", sa.Integer, nullable=True),
        sa.Column("answered", sa.Boolean, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_assistant_usage_user_created",
        "assistant_usage",
        ["user_id", "created_at"],
    )

    op.execute(
        """
        INSERT INTO assistant_usage
            (user_id, conversation_id, prompt_tokens, completion_tokens,
             total_tokens, answered, created_at)
        SELECT c.user_id, m.conversation_id, m.prompt_tokens,
               m.completion_tokens, m.total_tokens, (m.role = 'assistant'),
               m.created_at
        FROM assistant_messages m
        JOIN assistant_conversations c ON c.id = m.conversation_id
        WHERE m.role = 'assistant' OR m.total_tokens IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_assistant_usage_user_created", table_name="assistant_usage")
    op.drop_table("assistant_usage")
