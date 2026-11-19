"""Push notifications: the devices that receive them, the alerts still to send each one, and
the alert types each user mutes for push and Telegram.

Revision ID: 0030
Revises: 0029

  notification_preferences – (user, source) → enabled; no row means the type is on.
  push_subscriptions       – one row per browser or installed app, tied to its session.
  push_deliveries          – queue of (device, alert) pairs; a row is deleted once handled.
"""

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_preferences",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "source"),
    )

    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_version", sa.Integer(), nullable=False),
        sa.Column("session_jti", sa.String(64), nullable=False),
        sa.Column("endpoint", sa.String(2048), nullable=False),
        sa.Column("p256dh", sa.String(100), nullable=False),
        sa.Column("auth", sa.String(40), nullable=False),
        sa.Column("origin", sa.String(255), nullable=False),
        sa.Column("locale", sa.String(2), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("locale IN ('es', 'en')", name="ck_push_subscriptions_locale"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("endpoint", name="uq_push_subscriptions_endpoint"),
    )
    op.create_index("ix_push_subscriptions_user_id", "push_subscriptions", ["user_id"])
    op.create_index("ix_push_subscriptions_session_jti", "push_subscriptions", ["session_jti"])

    op.create_table(
        "push_deliveries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("notification_id", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["push_subscriptions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "subscription_id", "notification_id", name="uq_push_deliveries_target"
        ),
    )
    op.create_index("ix_push_deliveries_next_attempt_at", "push_deliveries", ["next_attempt_at"])
    op.create_index("ix_push_deliveries_notification_id", "push_deliveries", ["notification_id"])


def downgrade() -> None:
    op.drop_index("ix_push_deliveries_notification_id", table_name="push_deliveries")
    op.drop_index("ix_push_deliveries_next_attempt_at", table_name="push_deliveries")
    op.drop_table("push_deliveries")
    op.drop_index("ix_push_subscriptions_session_jti", table_name="push_subscriptions")
    op.drop_index("ix_push_subscriptions_user_id", table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
    op.drop_table("notification_preferences")
