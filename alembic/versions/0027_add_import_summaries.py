"""Add opt-in import analysis, durable delivery jobs and per-attempt AI usage."""

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_summary_settings",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("channel_id", sa.Integer(),
                  sa.ForeignKey("notification_channels.id", ondelete="SET NULL")),
        sa.Column("language", sa.String(2), nullable=False, server_default="en"),
    )
    op.create_table(
        "import_summary_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("import_run_id", sa.Integer(),
                  sa.ForeignKey("import_runs.id", ondelete="SET NULL")),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="SET NULL")),
        sa.Column("channel_id", sa.Integer(),
                  sa.ForeignKey("notification_channels.id", ondelete="SET NULL")),
        sa.Column("channel_version", sa.String(64), nullable=False),
        sa.Column("account_name", sa.String(100), nullable=False),
        sa.Column("from_date", sa.Date(), nullable=False),
        sa.Column("to_date", sa.Date(), nullable=False),
        sa.Column("language", sa.String(2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("generation_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("delivery_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("claim_token", sa.String(36)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("message_text", sa.Text()),
        sa.Column("error", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "import_run_id", name="uq_import_summary_user_run"),
    )
    op.create_index("ix_import_summary_jobs_due", "import_summary_jobs",
                    ["status", "next_attempt_at"])
    op.create_index("ix_import_summary_jobs_user", "import_summary_jobs",
                    ["user_id", "created_at"])
    op.create_table(
        "import_summary_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(),
                  sa.ForeignKey("import_summary_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("prompt_tokens", sa.Integer()),
        sa.Column("completion_tokens", sa.Integer()),
        sa.Column("total_tokens", sa.Integer()),
        sa.Column("answered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_import_summary_attempts_user_date", "import_summary_attempts",
                    ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_table("import_summary_attempts")
    op.drop_table("import_summary_jobs")
    op.drop_table("import_summary_settings")
