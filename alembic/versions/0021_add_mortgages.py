"""Add mortgage module tables.

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-06

Additive changes only — no existing table is touched.

  - mortgages              — loan contract (fixed / variable / mixed)
  - mortgage_rate_periods  — interest-rate tranches; models all three types uniformly
  - mortgage_bonuses       — linked-product discounts that reduce the effective spread
  - mortgage_prepayments   — lump-sum overpayments (reduce term / reduce payment)
  - euribor_rates          — monthly index series fetched from the ECB Data Portal
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. mortgages — parent of every other mortgage table
    op.create_table(
        "mortgages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("lender", sa.String(100), nullable=True),
        sa.Column("initial_principal", sa.Numeric(18, 2), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("term_months", sa.Integer(), nullable=False),
        sa.Column("payment_day", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("rate_type", sa.String(10), nullable=False),
        sa.Column(
            "amortization_system", sa.String(20), nullable=False, server_default="french"
        ),
        sa.Column("linked_account_id", sa.Integer(), nullable=True),
        sa.Column("linked_category_id", sa.Integer(), nullable=True),
        sa.Column("property_value", sa.Numeric(18, 2), nullable=True),
        sa.Column("property_value_date", sa.Date(), nullable=True),
        sa.Column(
            "include_in_net_worth", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["linked_account_id"], ["accounts.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["linked_category_id"], ["categories.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mortgages_user_id", "mortgages", ["user_id"])

    # 2. mortgage_rate_periods — fixed/variable tranches
    op.create_table(
        "mortgage_rate_periods",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("mortgage_id", sa.Integer(), nullable=False),
        sa.Column("start_month", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("fixed_rate", sa.Numeric(8, 5), nullable=True),
        sa.Column("index_name", sa.String(20), nullable=True),
        sa.Column("spread", sa.Numeric(8, 5), nullable=True),
        sa.Column("review_months", sa.Integer(), nullable=True),
        sa.Column("review_lag_months", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("floor_rate", sa.Numeric(8, 5), nullable=True),
        sa.Column("cap_rate", sa.Numeric(8, 5), nullable=True),
        sa.ForeignKeyConstraint(["mortgage_id"], ["mortgages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_mortgage_rate_periods_mortgage_id", "mortgage_rate_periods", ["mortgage_id"]
    )

    # 3. mortgage_bonuses — linked-product spread discounts
    op.create_table(
        "mortgage_bonuses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("mortgage_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "spread_reduction", sa.Numeric(8, 5), nullable=False, server_default="0"
        ),
        sa.Column("annual_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["mortgage_id"], ["mortgages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_mortgage_bonuses_mortgage_id", "mortgage_bonuses", ["mortgage_id"]
    )

    # 4. mortgage_prepayments — lump-sum overpayments
    op.create_table(
        "mortgage_prepayments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("mortgage_id", sa.Integer(), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("fee", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["mortgage_id"], ["mortgages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_mortgage_prepayments_mortgage_date",
        "mortgage_prepayments",
        ["mortgage_id", "payment_date"],
    )

    # 5. euribor_rates — monthly index series (ECB Data Portal)
    op.create_table(
        "euribor_rates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("index_name", sa.String(20), nullable=False),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("rate", sa.Numeric(8, 5), nullable=False),
        sa.Column("source", sa.String(20), nullable=False, server_default="ecb"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "index_name", "period", name="uq_euribor_rates_index_period"
        ),
    )
    op.create_index(
        "ix_euribor_rates_index_period", "euribor_rates", ["index_name", "period"]
    )


def downgrade() -> None:
    op.drop_index("ix_euribor_rates_index_period", table_name="euribor_rates")
    op.drop_table("euribor_rates")
    op.drop_index(
        "ix_mortgage_prepayments_mortgage_date", table_name="mortgage_prepayments"
    )
    op.drop_table("mortgage_prepayments")
    op.drop_index("ix_mortgage_bonuses_mortgage_id", table_name="mortgage_bonuses")
    op.drop_table("mortgage_bonuses")
    op.drop_index(
        "ix_mortgage_rate_periods_mortgage_id", table_name="mortgage_rate_periods"
    )
    op.drop_table("mortgage_rate_periods")
    op.drop_index("ix_mortgages_user_id", table_name="mortgages")
    op.drop_table("mortgages")
