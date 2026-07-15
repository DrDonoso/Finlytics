"""Add Fidelity ESPP tables and relax investment_connections.token_enc.

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-15

Additive changes:
  - investment_import_runs  — audit trail per CSV import
  - espp_lots               — immutable tax-lot per ESPP purchase row
  - price_history           — daily close cache (MSFT + EUR/USD FX)

Alter:
  - investment_connections.token_enc → NULLABLE
    (statement-import providers like Fidelity ESPP have no API token)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. investment_import_runs — must exist before espp_lots (no FK the other way)
    op.create_table(
        "investment_import_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("source_currency", sa.String(3), nullable=False),
        sa.Column("lots_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lots_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["investment_connections.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_hash", name="uq_investment_import_runs_file_hash"),
    )
    op.create_index(
        "ix_investment_import_runs_connection_id",
        "investment_import_runs",
        ["connection_id"],
    )

    # 2. espp_lots — immutable tax-lot record per CSV row
    op.create_table(
        "espp_lots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(10), nullable=False, server_default="MSFT"),
        sa.Column("purchase_date", sa.Date(), nullable=False),
        sa.Column("grant_date", sa.Date(), nullable=True),
        sa.Column("shares", sa.Numeric(18, 8), nullable=False),
        sa.Column("cost_basis", sa.Numeric(18, 2), nullable=False),
        sa.Column("cost_basis_per_share", sa.Numeric(18, 6), nullable=False),
        sa.Column("source_currency", sa.String(3), nullable=False),
        sa.Column("share_source", sa.String(2), nullable=False),
        sa.Column("holding_period", sa.String(50), nullable=True),
        sa.Column("dedup_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["investment_connections.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedup_hash", name="uq_espp_lots_dedup_hash"),
    )
    op.create_index(
        "ix_espp_lots_connection_purchase",
        "espp_lots",
        ["connection_id", "purchase_date"],
    )

    # 3. price_history — daily EOD close; serves both on-request cache and evolution series
    op.create_table(
        "price_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticker", sa.String(10), nullable=False),
        sa.Column("price_date", sa.Date(), nullable=False),
        sa.Column("close_usd", sa.Numeric(18, 6), nullable=False),
        sa.Column("fx_eur_usd", sa.Numeric(18, 6), nullable=False),
        sa.Column("close_eur", sa.Numeric(18, 6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ticker", "price_date", name="uq_price_history_ticker_date"
        ),
    )
    op.create_index(
        "ix_price_history_ticker_date",
        "price_history",
        ["ticker", "price_date"],
    )

    # 4. ALTER investment_connections.token_enc → NULLABLE
    #    Fidelity ESPP and future statement-import providers have no API token.
    op.alter_column(
        "investment_connections",
        "token_enc",
        existing_type=sa.Text(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "investment_connections",
        "token_enc",
        existing_type=sa.Text(),
        nullable=False,
    )
    op.drop_index("ix_price_history_ticker_date", table_name="price_history")
    op.drop_table("price_history")
    op.drop_index("ix_espp_lots_connection_purchase", table_name="espp_lots")
    op.drop_table("espp_lots")
    op.drop_index(
        "ix_investment_import_runs_connection_id",
        table_name="investment_import_runs",
    )
    op.drop_table("investment_import_runs")
