import json


def test_encrypted_backup_roundtrip_and_session_sanitization(client, setup_app, tmp_path):
    from lifeos.recovery import inspect_backup, restore_backup

    _, directory, _ = setup_app
    from lifeos.academic_models import Course, StudyDocument, Term
    from sqlalchemy.orm import Session

    with Session(setup_app[0].state.assistant.engine) as db:
        db.add(Term(id="term", name="Fixture term", start_date="2026-10-01", end_date="2027-01-01"))
        db.flush()
        db.add(Course(id="course", term_id="term", name="Fixture course"))
        db.flush()
        db.add(
            StudyDocument(
                id="document",
                course_id="course",
                filename="fixture.txt",
                content=b"original fixture bytes",
                created_at="2026-10-26T00:00:00Z",
                text_status="ready",
            )
        )
        db.commit()
    client.post("/tasks", json={"title": "Private fixture", "due": "2026-10-28"})
    response = client.post(
        "/recovery/backups", json={"password": "separate backup fixture password"}
    )
    assert response.status_code == 201
    metadata = response.json()
    downloaded = client.get(f"/recovery/backups/{metadata['id']}")
    assert downloaded.status_code == 200 and b"Private fixture" not in downloaded.content
    path = directory / "backups" / (metadata["id"] + ".lifeosbackup")
    info = inspect_backup(path, "separate backup fixture password")
    assert info["counts"]["tasks"] == 1 and info["counts"]["sessions"] == 0
    target = tmp_path / "restore-target"
    restore_backup(path, "separate backup fixture password", target)
    import sqlite3

    with sqlite3.connect(target / "lifeos.sqlite3") as db:
        assert db.execute("select title from tasks").fetchone()[0] == "Private fixture"
        assert db.execute("select count(*) from sessions").fetchone()[0] == 0
        assert (
            db.execute("select content from documents").fetchone()[0] == b"original fixture bytes"
        )
    assert client.get("/session").status_code == 200


def test_recovery_password_tamper_and_lock_fail_closed(client, setup_app, tmp_path):
    import pytest
    from lifeos.data_lock import data_lock
    from lifeos.recovery import RecoveryError, inspect_backup, restore_backup

    response = client.post("/recovery/backups", json={"password": "backup fixture password"})
    path = setup_app[1] / "backups" / (response.json()["id"] + ".lifeosbackup")
    with pytest.raises(RecoveryError):
        inspect_backup(path, "wrong backup password")
    modified = tmp_path / "tampered.lifeosbackup"
    data = bytearray(path.read_bytes())
    data[-1] ^= 1
    modified.write_bytes(data)
    with pytest.raises(RecoveryError):
        inspect_backup(modified, "backup fixture password")
    target = tmp_path / "locked-target"
    target.mkdir()
    with data_lock(target):
        with pytest.raises(RecoveryError):
            restore_backup(path, "backup fixture password", target)


def test_export_scope_and_protected_endpoints(client):
    client.post("/tasks", json={"title": "Portable task"})
    result = client.get("/recovery/export")
    assert result.status_code == 200 and "attachment" in result.headers["content-disposition"]
    data = json.loads(result.content)
    assert data["tasks"][0]["title"] == "Portable task"
    assert set(data) == {"format", "version", "created_at", "settings", "tasks", "events"}
    assert "password" not in result.text and "credentials" not in result.text
    short = client.post("/recovery/backups", json={"password": "short"})
    assert short.status_code == 422 and "short" not in short.text
    client.headers["X-CSRF-Token"] = "bad"
    assert (
        client.post("/recovery/backups", json={"password": "fixture password"}).status_code == 403
    )


def test_reviewed_backup_digest_binds_inspection_and_restore_to_exact_encrypted_bytes(
    client, setup_app, tmp_path
):
    import hashlib

    import pytest
    from lifeos.recovery import RecoveryError, inspect_backup, restore_backup

    password = "digest backup fixture password"
    client.post("/tasks", json={"title": "Reviewed fixture"})
    first = client.post("/recovery/backups", json={"password": password}).json()
    path = setup_app[1] / "backups" / (first["id"] + ".lifeosbackup")
    reviewed = path.read_bytes()
    digest = hashlib.sha256(reviewed).hexdigest()
    client.post("/tasks", json={"title": "Unreviewed replacement fixture"})
    second = client.post("/recovery/backups", json={"password": password}).json()
    path.write_bytes((setup_app[1] / "backups" / (second["id"] + ".lifeosbackup")).read_bytes())
    target = tmp_path / "restore-digest-target"
    with pytest.raises(RecoveryError, match="backup_changed"):
        inspect_backup(path, password, expected_sha256=digest)
    with pytest.raises(RecoveryError, match="backup_changed"):
        restore_backup(path, password, target, expected_sha256=digest)
    assert not (target / "lifeos.sqlite3").exists()
    path.write_bytes(reviewed)
    assert inspect_backup(path, password, expected_sha256=digest)["counts"]["tasks"] == 1
    assert restore_backup(path, password, target, expected_sha256=digest)["counts"]["tasks"] == 1
