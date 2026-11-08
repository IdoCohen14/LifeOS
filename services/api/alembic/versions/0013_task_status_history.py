"""Track status markings from upgrade onward; never backfill completion dates."""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"


def upgrade():
    op.create_table(
        "task_status_history",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "task_id", sa.String(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.Column("occurred_at", sa.String(), nullable=False),
    )
    op.create_index("ix_task_status_history_task_id", "task_status_history", ["task_id"])
    op.create_index("ix_task_status_history_occurred_at", "task_status_history", ["occurred_at"])
    op.create_table(
        "task_history_metadata",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tracking_started_at", sa.String(), nullable=False),
    )
    op.execute("INSERT INTO task_history_metadata VALUES(1,strftime('%Y-%m-%dT%H:%M:%fZ','now'))")
    for name, operation, condition in [
        ("task_status_insert", "INSERT", "NEW.completed=1"),
        ("task_status_update", "UPDATE OF completed", "OLD.completed<>NEW.completed"),
    ]:
        op.execute(f"""CREATE TRIGGER {name} AFTER {operation} ON tasks WHEN {condition}
        BEGIN
          INSERT INTO task_status_history(id,task_id,completed,occurred_at)
          VALUES(lower(hex(randomblob(16))),NEW.id,NEW.completed,strftime('%Y-%m-%dT%H:%M:%fZ','now'));
          DELETE FROM task_status_history WHERE occurred_at<strftime('%Y-%m-%dT%H:%M:%fZ','now','-90 days');
        END""")


def downgrade():
    op.execute("DROP TRIGGER task_status_insert")
    op.execute("DROP TRIGGER task_status_update")
    op.drop_table("task_status_history")
    op.drop_table("task_history_metadata")
