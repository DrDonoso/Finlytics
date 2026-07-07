"""Add tag emoji field and category color field.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-06

This migration is PURELY ADDITIVE:
- Adds ``tags.emoji`` (nullable VARCHAR(16)) — emoji as a first-class field,
  separate from the tag name.
- Adds ``categories.color`` (VARCHAR(7) NOT NULL, default '#64748b') for
  per-category colour theming.
- Backfills existing tags whose name starts with a Unicode emoji/pictograph
  (e.g. "💡 luz" → emoji='💡', name='luz').  Conservative: only splits when
  there is a clear leading emoji followed by a non-empty text remainder.
  Normal alphanumeric names ("internet", "teléfono") are untouched.

Safe to apply on a live DB that already has tags, categories, and transaction data
from revision 0003.  No rows are deleted; only nullable column added + data moved.
"""

import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Match a leading run of emoji/pictograph code points followed by optional
# whitespace and a non-empty text remainder.
# Covered Unicode ranges:
#   U+2600-U+27BF  — Miscellaneous Symbols, Dingbats
#   U+1F300-U+1F9FF — Emoji (all blocks: faces, nature, food, travel, objects…)
#   U+1FA00-U+1FAFF — Chess symbols, extended emoji
# We require that the remainder (after the emoji + optional space) is non-empty
# so that an emoji-only tag name is left unchanged.
_EMOJI_LEAD_RE = re.compile(
    r"^([\U0001F300-\U0001F9FF\U0001FA00-\U0001FAFF\u2600-\u27BF]+)\s*(.+)$",
    re.UNICODE,
)


def upgrade() -> None:
    # ── 1. Add tags.emoji (nullable VARCHAR(16)) ──────────────────────────────
    op.add_column("tags", sa.Column("emoji", sa.String(length=16), nullable=True))

    # ── 2. Add categories.color (NOT NULL, server_default neutral grey) ───────
    op.add_column(
        "categories",
        sa.Column(
            "color",
            sa.String(length=7),
            nullable=False,
            server_default="#64748b",
        ),
    )

    # ── 3. Backfill: split leading emoji out of existing tag names ────────────
    # Uses synchronous connection provided by `connection.run_sync(do_run_migrations)`
    # in alembic/env.py — op.get_bind() is correct here.
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, name FROM tags")).fetchall()
    for tag_id, name in rows:
        m = _EMOJI_LEAD_RE.match(name)
        if m:
            emoji_part = m.group(1)
            new_name = m.group(2).strip()
            if new_name:  # safety guard: never leave an empty name
                conn.execute(
                    sa.text(
                        "UPDATE tags SET emoji = :emoji, name = :name WHERE id = :id"
                    ),
                    {"emoji": emoji_part, "name": new_name, "id": tag_id},
                )


def downgrade() -> None:
    op.drop_column("categories", "color")
    op.drop_column("tags", "emoji")
