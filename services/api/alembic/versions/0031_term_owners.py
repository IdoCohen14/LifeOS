"""Academic ownership root; existing terms remain unassigned."""

from alembic import op

revision = "0031"
down_revision = "0030"


def upgrade():
    op.execute("ALTER TABLE terms ADD COLUMN account_id VARCHAR REFERENCES accounts(id)")
    op.create_index("ix_terms_account_id", "terms", ["account_id"])


def downgrade():
    op.drop_index("ix_terms_account_id", table_name="terms")
    op.execute("ALTER TABLE terms DROP COLUMN account_id")
