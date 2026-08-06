"""Add signature_date to mortgages.

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-06

A Spanish mortgage signed mid-month charges interest alone for the days between
signature and the first payment date; capital only starts amortizing with the
following instalment. Without the signature date the engine treats that opening
charge as a full instalment, amortizing capital that was never repaid — roughly
600 EUR of phantom principal on a 291.200 EUR loan, and a schedule that ends a
month early.

Nullable: an existing mortgage keeps its current behaviour, which is the right
model for a loan whose first charge really was a full instalment.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("mortgages", sa.Column("signature_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("mortgages", "signature_date")
