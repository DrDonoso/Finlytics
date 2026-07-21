"""Add is_system column to transactions; backfill opening-balance rows.

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-21

Adds a Boolean flag ``is_system`` (non-nullable, default false) to the
``transactions`` table to mark synthetic rows created by Finlytics itself
(e.g. "Saldo inicial" opening-balance entries).  System transactions are
excluded from all KPI and flow-analysis aggregations so they never inflate
income figures.

Backfill: any existing transaction linked to an ImportRun whose
``source_filename`` is ``'manual:saldo-inicial'`` is flagged retroactively.
This signal is reliable — it is the stable identity set by
``create_opening_balance_tx`` and never reused for real user data.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column(
            "is_system",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # Backfill existing opening-balance transactions.
    # Uses the import_run source_filename signal — the only reliable, stable
    # marker that distinguishes synthetic rows from real user data.
    op.execute(
        """
        UPDATE transactions
        SET is_system = true
        WHERE import_run_id IN (
            SELECT id FROM import_runs
            WHERE source_filename = 'manual:saldo-inicial'
        )
        """
    )


def downgrade() -> None:
    op.drop_column("transactions", "is_system")
