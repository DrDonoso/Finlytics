"""What's new: the notes each user has read (``users.whats_new_seen``).

NULL means the interface never recorded any, as for a new user: it then marks every current note
as read without showing them.  Existing users get an empty list instead, so the next time they
open Finlytics they read the notes that come with this version.
"""
import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("whats_new_seen", sa.JSON(), nullable=True))
    users = sa.table("users", sa.column("whats_new_seen", sa.JSON()))
    op.execute(users.update().values(whats_new_seen=[]))


def downgrade() -> None:
    op.drop_column("users", "whats_new_seen")
