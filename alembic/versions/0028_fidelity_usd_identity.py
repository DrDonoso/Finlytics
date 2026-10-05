"""Re-key Fidelity lots independently of costs without deleting existing data."""
from collections import defaultdict
import hashlib

from alembic import op
import sqlalchemy as sa

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("espp_lots", sa.Column("dedup_ordinal", sa.Integer(), nullable=False, server_default="0"))
    op.drop_constraint("uq_investment_import_runs_file_hash", "investment_import_runs", type_="unique")
    op.create_unique_constraint(
        "uq_investment_import_runs_connection_file",
        "investment_import_runs", ["connection_id", "file_hash"],
    )
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, connection_id, ticker, purchase_date, shares, share_source, grant_date "
        "FROM espp_lots ORDER BY id"
    )).mappings()
    ordinals = defaultdict(int)
    for row in rows:
        key = (
            row["connection_id"], row["ticker"], row["purchase_date"],
            row["shares"], row["share_source"], row["grant_date"],
        )
        ordinal = ordinals[key]
        ordinals[key] += 1
        payload = (
            f"fidelity:v2|{row['connection_id']}|{row['ticker']}|{row['purchase_date']}"
            f"|{row['shares']:.8f}|{row['share_source']}|{row['grant_date'] or ''}|{ordinal}"
        )
        conn.execute(
            sa.text("UPDATE espp_lots SET dedup_hash = :hash, dedup_ordinal = :ordinal WHERE id = :id"),
            {"hash": hashlib.sha256(payload.encode("utf-8")).hexdigest(), "ordinal": ordinal, "id": row["id"]},
        )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM espp_lots) OR EXISTS (SELECT 1 FROM investment_import_runs)"
    )).scalar():
        raise RuntimeError("Restore a pre-0028 backup before downgrading populated Fidelity data.")
    op.drop_column("espp_lots", "dedup_ordinal")
    op.drop_constraint("uq_investment_import_runs_connection_file", "investment_import_runs", type_="unique")
    op.create_unique_constraint(
        "uq_investment_import_runs_file_hash", "investment_import_runs", ["file_hash"],
    )
