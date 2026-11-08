"""Manual academic records and local document index."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade():
    op.create_table(
        "terms",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("start_date", sa.String(), nullable=False),
        sa.Column("end_date", sa.String(), nullable=False),
    )
    op.create_table(
        "courses",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("term_id", sa.String(), sa.ForeignKey("terms.id"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("instructor", sa.String(120), nullable=False),
        sa.Column("credits", sa.Float(), nullable=False),
        sa.Column("color", sa.String(7), nullable=False),
    )
    op.create_index("ix_courses_term_id", "courses", ["term_id"])
    op.create_table(
        "academic_items",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("course_id", sa.String(), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("task_id", sa.String(), sa.ForeignKey("tasks.id"), nullable=False, unique=True),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("due", sa.String(), nullable=False),
        sa.Column("effort_hours", sa.Float(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
    )
    op.create_index("ix_academic_items_course_id", "academic_items", ["course_id"])
    op.create_index("ix_academic_items_due", "academic_items", ["due"])
    op.create_table(
        "timetable",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("course_id", sa.String(), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.String(5), nullable=False),
        sa.Column("end_time", sa.String(5), nullable=False),
        sa.Column("timezone", sa.String(80), nullable=False),
        sa.Column("location", sa.String(240), nullable=False),
    )
    op.create_index("ix_timetable_course_id", "timetable", ["course_id"])
    op.create_table(
        "grades",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("course_id", sa.String(), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("maximum", sa.Float(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=True),
    )
    op.create_index("ix_grades_course_id", "grades", ["course_id"])
    op.create_table(
        "documents",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("course_id", sa.String(), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("filename", sa.String(240), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("text_status", sa.String(30), nullable=False),
    )
    op.create_index("ix_documents_course_id", "documents", ["course_id"])
    op.create_table(
        "document_sections",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reference", sa.String(80), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
    )
    op.create_index("ix_document_sections_document_id", "document_sections", ["document_id"])
    op.execute(
        "CREATE VIRTUAL TABLE document_search USING fts5(section_id UNINDEXED, document_id UNINDEXED, text, tokenize='unicode61')"
    )
    op.execute(
        "CREATE TRIGGER document_section_insert AFTER INSERT ON document_sections BEGIN INSERT INTO document_search(section_id,document_id,text) VALUES(new.id,new.document_id,new.text); END"
    )
    op.execute(
        "CREATE TRIGGER document_section_delete AFTER DELETE ON document_sections BEGIN DELETE FROM document_search WHERE section_id=old.id; END"
    )


def downgrade():
    op.execute("DROP TRIGGER document_section_delete")
    op.execute("DROP TRIGGER document_section_insert")
    op.execute("DROP TABLE document_search")
    for table in (
        "document_sections",
        "documents",
        "grades",
        "timetable",
        "academic_items",
        "courses",
        "terms",
    ):
        op.drop_table(table)
