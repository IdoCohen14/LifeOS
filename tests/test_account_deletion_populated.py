from lifeos.academic_models import DocumentSection, StudyDocument
from lifeos.account_academic import AccountAcademic
from lifeos.account_archive import AccountArchive
from lifeos.account_deletion import owned_filters
from lifeos.account_lifecycle import AccountLifecycleService
from lifeos.account_records import AccountRecords
from lifeos.accounts import AccountService
from lifeos.assistant_models import AssistantProposal
from lifeos.db import Base, migrate, open_database
from lifeos.models import AccountPreference, AccountProvider, AccountProviderRecord
from lifeos.security import token_hash
from lifeos.series_models import EventSeries, SeriesOccurrence
from lifeos.task_history_models import TaskStatusHistory  # noqa: F401
from lifeos.task_planning_models import TaskTimeBlock
from lifeos.web_push_models import AccountPushConfig, AccountPushDelivery, AccountPushDevice
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session


def test_populated_deletion_removes_indirect_rows_and_preserves_other_owner(tmp_path):
    engine = open_database(tmp_path)
    migrate(engine)
    auth = AccountService(engine, enabled=True)
    lifecycle = AccountLifecycleService(auth, tmp_path)
    academic, records, archive = (
        AccountAcademic(engine),
        AccountRecords(engine),
        AccountArchive(engine, tmp_path),
    )
    owners, sessions = [], []
    try:
        for suffix in ("a", "b"):
            owner = auth.register("populated-" + suffix, "fixture password")
            signed = auth.login("populated-" + suffix, "fixture password")
            owners.append(owner)
            sessions.append(signed)
            term = academic.save_root(
                owner,
                "terms",
                {"name": "Term", "start_date": "2026-10-01", "end_date": "2027-01-31"},
            )
            course = academic.save_root(owner, "courses", {"term_id": term["id"], "name": "Course"})
            academic.save_child(
                owner,
                "items",
                {"course_id": course["id"], "title": "Assignment", "due": "2026-11-03"},
            )
            academic.save_child(
                owner,
                "grades",
                {"course_id": course["id"], "title": "Grade", "score": 80, "maximum": 100},
            )
            academic.save_child(
                owner,
                "timetable",
                {
                    "course_id": course["id"],
                    "weekday": 0,
                    "start_time": "10:00",
                    "end_time": "11:00",
                    "timezone": "Asia/Jerusalem",
                },
            )
            task = records.save(owner, "tasks", {"title": "Manual fixture"})
            event = records.save(
                owner,
                "events",
                {
                    "title": "Event",
                    "start": "2026-11-03T10:00:00+02:00",
                    "end": "2026-11-03T11:00:00+02:00",
                },
            )
            with Session(engine) as db:
                db.add_all(
                    [
                        StudyDocument(
                            id="doc-" + suffix,
                            course_id=course["id"],
                            filename="fixture.txt",
                            content=b"synthetic",
                            created_at="2026-10-30T00:00:00Z",
                            text_status="ready",
                        ),
                        AccountProvider(
                            account_id=owner,
                            provider="google",
                            credentials=b"synthetic",
                            authorized=True,
                        ),
                        EventSeries(
                            id="series-" + suffix,
                            account_id=owner,
                            title="Series",
                            timezone="Asia/Jerusalem",
                            created_at="2026-10-30T00:00:00Z",
                        ),
                        AccountPushConfig(
                            id=owner,
                            public_key="synthetic",
                            private_key=b"synthetic",
                            contact="fixture@example.test",
                            revision=1,
                        ),
                        AccountPushDevice(
                            id="device-" + suffix,
                            account_id=owner,
                            endpoint_hash="fixture",
                            subscription=b"synthetic",
                            last_seen=0,
                        ),
                        AccountPreference(
                            account_id=owner, kind="backup_schedule", revision=1, payload="{}"
                        ),
                        AssistantProposal(
                            id="proposal-" + suffix,
                            session_hash=token_hash(signed["token"]),
                            kind="task",
                            payload="{}",
                            expires=9999999999,
                        ),
                    ]
                )
                db.flush()
                db.add_all(
                    [
                        DocumentSection(
                            id="section-" + suffix,
                            document_id="doc-" + suffix,
                            reference="1",
                            position=0,
                            text="synthetic searchable fixture",
                        ),
                        AccountProviderRecord(
                            account_id=owner, provider="google", external_id="fixture", payload="{}"
                        ),
                        SeriesOccurrence(event_id=event["id"], series_id="series-" + suffix),
                        TaskTimeBlock(task_id=task["id"], event_id=event["id"]),
                        AccountPushDelivery(
                            id="delivery-" + suffix, device_id="device-" + suffix, created_at=0
                        ),
                    ]
                )
                db.commit()
            lifecycle.generate_key(owner, signed["token"], "fixture password")
            archive.create(owner, "fixture backup password")

        def counts(db, owner):
            return {
                name: db.scalar(
                    select(func.count()).select_from(Base.metadata.tables[name]).where(predicate)
                )
                for name, predicate in owned_filters(owner).items()
            }

        with Session(engine) as db:
            other_counts = counts(db, owners[1])
        preview = lifecycle.deletion_preview(owners[0], sessions[0]["token"])
        assert (
            preview["counts"]["documents"] == 1
            and preview["counts"]["account_push_deliveries"] == 1
        )
        assert lifecycle.confirm_deletion(
            owners[0], sessions[0]["token"], preview["id"], "fixture password", "populated-a"
        )["deleted"]
        with Session(engine) as db:
            assert db.execute(text("pragma foreign_key_check")).all() == []
            assert (
                db.execute(
                    text("select count(*) from document_search where document_id='doc-a'")
                ).scalar()
                == 0
            )
            assert all(value == 0 for value in counts(db, owners[0]).values())
            assert counts(db, owners[1]) == other_counts
        assert len(archive.list(owners[1])) == 1
    finally:
        engine.dispose()
