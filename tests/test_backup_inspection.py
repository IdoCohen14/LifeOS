PASSWORD = "inspection fixture backup password"


def saved(client):
    result = client.post("/recovery/backups", json={"password": PASSWORD})
    assert result.status_code == 201
    return result.json()["id"]


def test_inspect_saved_backup_is_read_only_and_clears_temporary_plaintext(client, setup_app):
    task = client.post("/tasks", json={"title": "Inspection fixture title"}).json()
    id = saved(client)
    response = client.post(f"/recovery/backups/{id}/inspect", json={"password": PASSWORD})
    assert response.status_code == 200
    value = response.json()
    assert value["valid"] and value["counts"]["tasks"] == 1 and value["counts"]["events"] == 0
    assert "Inspection fixture title" not in response.text and PASSWORD not in response.text
    assert client.get("/tasks").json() == [task]
    assert client.get("/session").status_code == 200
    assert not list((setup_app[1] / "backups").glob(".recovery-*"))


def test_inspect_wrong_password_auth_csrf_and_slot_are_honest(client, setup_app):
    from lifeos.data_lock import backup_lock

    id = saved(client)
    url = f"/recovery/backups/{id}/inspect"
    response = client.post(url, json={"password": "wrong fixture password"})
    assert response.status_code == 422 and "wrong fixture password" not in response.text
    with backup_lock(setup_app[1]):
        assert client.post(url, json={"password": PASSWORD}).status_code == 409
    token = client.headers.pop("X-CSRF-Token")
    assert client.post(url, json={"password": PASSWORD}).status_code == 403
    client.headers["X-CSRF-Token"] = token
    assert (
        client.post(
            "/recovery/backups/00000000-0000-0000-0000-000000000000/inspect",
            json={"password": PASSWORD},
        ).status_code
        == 404
    )
    client.cookies.clear()
    assert client.post(url, json={"password": PASSWORD}).status_code == 401


def test_inspect_rejects_unsafe_path_and_malformed_manifest_time(client, setup_app, monkeypatch):
    from pathlib import Path

    from lifeos import backup_inspection

    id = saved(client)
    url = f"/recovery/backups/{id}/inspect"
    original = Path.is_symlink
    monkeypatch.setattr(
        Path, "is_symlink", lambda path: path.name == id + ".lifeosbackup" or original(path)
    )
    assert client.post(url, json={"password": PASSWORD}).status_code == 404
    monkeypatch.setattr(Path, "is_symlink", original)
    monkeypatch.setattr(
        backup_inspection,
        "inspect_backup",
        lambda *args: {
            "schema": "0018",
            "counts": {"tasks": 0, "events": 0},
            "created_at": "not-a-date",
        },
    )
    assert client.post(url, json={"password": PASSWORD}).status_code == 422
    monkeypatch.setattr(
        backup_inspection,
        "inspect_backup",
        lambda *args: {
            "schema": "0018",
            "counts": {"tasks": 0, "events": 0},
            "created_at": "2026-10-27T10:00:00",
        },
    )
    assert client.post(url, json={"password": PASSWORD}).status_code == 422
    assert (
        client.post(
            "/recovery/backups/not-a-canonical-uuid/inspect", json={"password": PASSWORD}
        ).status_code
        == 404
    )


def test_inspect_bad_request_never_echoes_password_or_extra_fields(client):
    id = saved(client)
    response = client.post(
        f"/recovery/backups/{id}/inspect",
        json={"password": "inspection private short", "unexpected": "private fixture"},
    )
    assert response.status_code == 422
    assert (
        "inspection private short" not in response.text and "private fixture" not in response.text
    )


def test_inspect_rejects_redirected_backup_directory(client, setup_app):
    import os
    import subprocess

    import pytest
    from fastapi import HTTPException
    from lifeos.backup_inspection import inspect_saved

    id = saved(client)
    private = setup_app[1] / "separate-private"
    private.mkdir()
    link = private / "backups"
    target = setup_app[1] / "backups"
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            creationflags=0x08000000,
        )
        assert result.returncode == 0
    else:
        link.symlink_to(target, target_is_directory=True)
    with pytest.raises(HTTPException) as error:
        inspect_saved(private, id, PASSWORD)
    assert error.value.status_code == 404


def test_actual_encrypted_corrupt_sqlite_returns_invalid_not_retryable(client, setup_app):
    import io
    import os
    import zipfile

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from lifeos import recovery

    id = saved(client)
    path = setup_app[1] / "backups" / (id + ".lifeosbackup")
    entries, _ = recovery.unpack_backup(path, PASSWORD)
    entries["lifeos.sqlite3"] = b"not a SQLite database fixture"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    salt, nonce = os.urandom(16), os.urandom(12)
    header = recovery.MAGIC + salt + nonce
    path.write_bytes(
        header + AESGCM(recovery.derive(PASSWORD, salt)).encrypt(nonce, buffer.getvalue(), header)
    )
    response = client.post(f"/recovery/backups/{id}/inspect", json={"password": PASSWORD})
    assert response.status_code == 422
    assert not list((setup_app[1] / "backups").glob(".recovery-*"))
