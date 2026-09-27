"""Recolour the base categories with a colour-blind-safe palette.

Revision ID: 0025
Revises: 0024
Create Date: 2026-09-27

The original palette put several categories within a hair of each other. Under
normal vision Dining sat within ΔE00 8 of both Shopping and Bank Fees; under
simulated protanopia Insurance and Subscriptions were ΔE00 0.7 apart, and under
deuteranopia Transport and Insurance 1.8 — the same colour, in practice, in the
spending donut. Taxes, Housing and Education also fell below 3:1 against the
dark card surface.

The replacement keeps every pair at least ΔE00 12 apart under normal vision and
7.5 under simulated deuteranopia and protanopia, and clears 3:1 against the dark
surface. Only a colour still equal to its seeded original is replaced, so a
category the user recoloured keeps their choice. The downgrade mirrors that.
"""

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

log = logging.getLogger("alembic.runtime.migration")

# name: (seeded before 0025, seeded from 0025 on)
PALETTE: dict[str, tuple[str, str]] = {
    "Groceries": ("#22c55e", "#70912f"),
    "Dining": ("#ef4444", "#b94644"),
    "Transport": ("#3b82f6", "#4f86c6"),
    "Fuel": ("#f97316", "#e65909"),
    "Housing": ("#92400e", "#bd9670"),
    "Utilities": ("#0d9488", "#2bccb4"),
    "Health": ("#ec4899", "#e3a8b4"),
    "Insurance": ("#8b5cf6", "#6f69a3"),
    "Shopping": ("#f43f5e", "#d77089"),
    "Entertainment": ("#eab308", "#cf7ffd"),
    "Subscriptions": ("#6366f1", "#4963de"),
    "Travel": ("#0ea5e9", "#47a4b4"),
    "Education": ("#1d4ed8", "#c6c102"),
    "Income": ("#10b981", "#26795f"),
    "Transfers": ("#94a3b8", "#97bd95"),
    "Investments": ("#d97706", "#049886"),
    "Bank Fees": ("#dc2626", "#9f696f"),
    "Taxes": ("#475569", "#896385"),
    "Cash/ATM": ("#84cc16", "#d1b876"),
    "Other": ("#a78bfa", "#bdb0ef"),
}

_RECOLOR = sa.text(
    "UPDATE categories SET color = :to_color "
    "WHERE name = :name AND is_base IS TRUE AND lower(color) = :from_color"
)


def _recolor(forward: bool) -> None:
    bind = op.get_bind()
    changed = 0
    for name, (old, new) in PALETTE.items():
        from_color, to_color = (old, new) if forward else (new, old)
        result = bind.execute(
            _RECOLOR, {"name": name, "from_color": from_color, "to_color": to_color}
        )
        changed += result.rowcount or 0
    log.info("0025: %d base category colour(s) replaced", changed)


def upgrade() -> None:
    _recolor(forward=True)


def downgrade() -> None:
    _recolor(forward=False)
