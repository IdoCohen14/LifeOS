"""Session-bound receipts for reviewed atomic course batches."""

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"


def upgrade():
    op.create_table(
        "course_batches",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "session_hash",
            sa.String(),
            sa.ForeignKey("sessions.token_hash", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("payload", sa.String(), nullable=False),
        sa.Column("expires", sa.Integer(), nullable=False),
        sa.Column("result", sa.String(), nullable=True),
    )
    op.create_index("ix_course_batches_session_hash", "course_batches", ["session_hash"])


def downgrade():
    op.drop_index("ix_course_batches_session_hash", table_name="course_batches")
    op.drop_table("course_batches")
