import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from types import SimpleNamespace

import pytest
from test_academic import course_fixture
from test_documents import upload


def test_extraction_timeout_is_bounded(tmp_path, monkeypatch):
    from lifeos import documents

    script = tmp_path / "slow_fixture.py"
    script.write_text("import os,time\nprint(os.getpid(),flush=True)\ntime.sleep(4)\n")
    monkeypatch.setattr(documents, "EXTRACTOR_SCRIPT", script)
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired) as error:
        documents.run_extractor(b"fixture", ".txt", timeout=0.5)
    assert time.monotonic() - started < 3
    assert error.value.output.strip().isdigit()


def test_parallel_extraction_is_bounded_and_reusable(client, monkeypatch):
    _, course = course_fixture(client)
    entered, release = Event(), Event()
    lock = Lock()
    calls = 0

    def slow(*args, **kwargs):
        nonlocal calls
        with lock:
            calls += 1
            if calls == 2:
                entered.set()
        assert release.wait(5)
        return SimpleNamespace(returncode=0, stdout=b'{"status":"no_text","sections":[]}')

    monkeypatch.setattr("lifeos.documents.run_extractor", slow)
    with ThreadPoolExecutor(max_workers=3) as pool:
        pending = [pool.submit(upload, client, course, "fixture.txt", b"fixture") for _ in range(2)]
        try:
            assert entered.wait(3)
            rejected = pool.submit(upload, client, course, "fixture.txt", b"fixture").result(
                timeout=2
            )
            assert rejected.status_code == 429 and rejected.headers["Retry-After"] == "1"
            assert calls == 2
        finally:
            release.set()
        assert [future.result().status_code for future in pending] == [201, 201]
    assert upload(client, course, "fixture.txt", b"fixture").status_code == 201


def test_failed_extraction_releases_capacity_without_persisting_document(client, monkeypatch):
    _, course = course_fixture(client)

    def broken(*args, **kwargs):
        raise subprocess.TimeoutExpired("fixture", 12)

    monkeypatch.setattr("lifeos.documents.run_extractor", broken)
    for _ in range(2):
        assert upload(client, course, "fixture.txt", b"fixture").status_code == 422
    assert client.get("/academic/documents").json() == []
    monkeypatch.setattr(
        "lifeos.documents.run_extractor",
        lambda *args: SimpleNamespace(returncode=0, stdout=b'{"status":"no_text","sections":[]}'),
    )
    assert upload(client, course, "fixture.txt", b"fixture").status_code == 201
