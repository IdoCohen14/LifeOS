"""Local expiring recommendation dismissals."""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"


def upgrade():
    op.create_table(
        "recommendation_dismissals",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("expires", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_recommendation_dismissals_expires", "recommendation_dismissals", ["expires"]
    )


def downgrade():
    op.drop_table("recommendation_dismissals")
