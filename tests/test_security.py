import pytest
from lifeos.security import initialize_password, verify_password


def test_eight_character_password_is_accepted(tmp_path):
    initialize_password(tmp_path, "abcdefgh")
    assert verify_password(tmp_path, "abcdefgh")
    assert not verify_password(tmp_path, "wrongpass")


def test_seven_character_password_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="at least 8 characters"):
        initialize_password(tmp_path, "abcdefg")
    assert not (tmp_path / "auth.json").exists()


def test_setup_rejects_password_longer_than_login_accepts(tmp_path):
    with pytest.raises(ValueError, match="at most 1024"):
        initialize_password(tmp_path, "x" * 1025)
    assert not (tmp_path / "auth.json").exists()


def test_setup_accepts_maximum_login_password_length(tmp_path):
    initialize_password(tmp_path, "x" * 1024)
    assert verify_password(tmp_path, "x" * 1024)


def test_validation_errors_do_not_echo_passwords_or_private_payloads(client):
    secret = "synthetic-private-password-" * 50
    response = client.post("/session", json={"password": secret})
    assert response.status_code == 422
    assert "synthetic-private-password" not in response.text
    assert response.json() == {"detail": "Invalid request"}

    assert response.headers["cache-control"] == "no-store"

    payload = {"title": "private fixture title", "priority": "private-invalid-value"}
    response = client.post("/tasks", json=payload)
    assert response.status_code == 422
    assert "private" not in response.text
    response = client.post(
        "/tasks",
        content='{"title":"private malformed fixture",',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request"}


def test_parallel_password_checks_are_bounded(setup_app, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event, Lock

    from fastapi.testclient import TestClient

    app, _, _ = setup_app
    entered = Event()
    release = Event()
    lock = Lock()
    active = 0

    def slow_verify(*args):
        nonlocal active
        with lock:
            active += 1
            if active == 2:
                entered.set()
        assert release.wait(5)
        return False

    monkeypatch.setattr("lifeos.main.verify_password", slow_verify)
    with TestClient(
        app, base_url="http://127.0.0.1:8000", headers={"X-LifeOS-Key": "test-process-key"}
    ) as client:
        with ThreadPoolExecutor(max_workers=3) as pool:
            pending = [
                pool.submit(client.post, "/session", json={"password": "fixture"}) for _ in range(2)
            ]
            try:
                assert entered.wait(3)
                rejected = pool.submit(
                    client.post, "/session", json={"password": "fixture"}
                ).result(timeout=2)
                assert rejected.status_code == 429
                assert rejected.headers["Retry-After"] == "1"
                assert active == 2
            finally:
                release.set()
            assert [future.result().status_code for future in pending] == [401, 401]
        assert client.post("/session", json={"password": "fixture"}).status_code == 401


def test_login_attempt_limit_rejects_without_hashing_again(client, monkeypatch):
    calls = 0

    def reject(*args):
        nonlocal calls
        calls += 1
        return False

    monkeypatch.setattr("lifeos.main.verify_password", reject)
    for _ in range(10):
        assert client.post("/session", json={"password": "fixture"}).status_code == 401
    assert client.post("/session", json={"password": "fixture"}).status_code == 429
    assert calls == 10


def test_password_slots_release_when_verification_raises(client, monkeypatch):
    def broken(*args):
        raise RuntimeError("fixture verification failure")

    monkeypatch.setattr("lifeos.main.verify_password", broken)
    for _ in range(2):
        with pytest.raises(RuntimeError, match="fixture verification failure"):
            client.post("/session", json={"password": "fixture"})
    monkeypatch.setattr("lifeos.main.verify_password", lambda *args: False)
    assert client.post("/session", json={"password": "fixture"}).status_code == 401


def test_login_attempt_window_expires_at_sixty_seconds(client, monkeypatch):
    import time
    from types import SimpleNamespace

    tick = 100.0
    monkeypatch.setattr("lifeos.main.time", SimpleNamespace(time=time.time, monotonic=lambda: tick))
    monkeypatch.setattr("lifeos.main.verify_password", lambda *args: False)
    for _ in range(10):
        assert client.post("/session", json={"password": "fixture"}).status_code == 401
    tick = 159.99
    assert client.post("/session", json={"password": "fixture"}).status_code == 429
    tick = 160.0
    assert client.post("/session", json={"password": "fixture"}).status_code == 401
