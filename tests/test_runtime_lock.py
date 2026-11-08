import pytest
from lifeos.data_lock import data_lock


def test_live_api_blocks_recovery_without_launcher(client, setup_app):
    with pytest.raises(RuntimeError, match="close_lifeos"):
        with data_lock(setup_app[1]):
            pytest.fail("A live API must block offline restore")


def test_runtime_readers_coexist_but_exclude_recovery(tmp_path):
    from lifeos.data_lock import runtime_lock

    with runtime_lock(tmp_path):
        with runtime_lock(tmp_path):
            with pytest.raises(RuntimeError):
                with data_lock(tmp_path):
                    pytest.fail("Recovery must be exclusive")
    with data_lock(tmp_path):
        with pytest.raises(RuntimeError):
            with runtime_lock(tmp_path):
                pytest.fail("Runtime cannot start during recovery")


def test_runtime_blocks_incomplete_recovery(tmp_path):
    from lifeos.data_lock import runtime_lock

    (tmp_path / ".restore-in-progress").write_text("fixture marker")
    with pytest.raises(RuntimeError, match="complete_recovery"):
        with runtime_lock(tmp_path):
            pytest.fail("Incomplete recovery must be completed offline")


@pytest.mark.parametrize("provider", ["google", "gmail", "moodle"])
def test_background_sync_blocks_recovery_after_api_lifespan_ends(setup_app, monkeypatch, provider):
    from threading import Event, Thread

    from fastapi.testclient import TestClient

    app, directory, _ = setup_app
    service = getattr(app.state, provider)
    entered, release = Event(), Event()
    failures = []

    def slow_sync():
        entered.set()
        assert release.wait(5)

    monkeypatch.setattr(service, "_sync", slow_sync)

    def run():
        try:
            service.sync()
        except Exception as error:
            failures.append(error)

    thread = Thread(target=run)
    try:
        with TestClient(app):
            thread.start()
            assert entered.wait(3)
        with pytest.raises(RuntimeError):
            with data_lock(directory):
                pytest.fail("Outstanding sync must retain its own runtime guard")
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive() and failures == []
    with data_lock(directory):
        pass


def test_worker_holds_runtime_guard_during_scheduler(setup_app, monkeypatch):
    import importlib.util
    from pathlib import Path

    directory = setup_app[1]
    path = Path(__file__).resolve().parents[1] / "services/worker/worker.py"
    spec = importlib.util.spec_from_file_location("fixture_worker", path)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)

    class Scheduler:
        def __init__(self, **kwargs):
            pass

        def add_job(self, *args, **kwargs):
            pass

        def start(self):
            with pytest.raises(RuntimeError):
                with data_lock(directory):
                    pytest.fail("Worker must block recovery while idle as well")

    monkeypatch.setattr(worker, "BlockingScheduler", Scheduler)
    worker.main()
    with data_lock(directory):
        pass


def test_orphan_runtime_retains_lock_after_launcher_parent_dies(tmp_path):
    import os
    import subprocess
    import sys
    import time
    from pathlib import Path

    child_code = """
import sys,time
from pathlib import Path
from lifeos.data_lock import runtime_lock
with runtime_lock(Path(sys.argv[1])):
    print('ready',flush=True)
    while not Path(sys.argv[2]).exists(): time.sleep(.02)
"""
    parent_code = """
import subprocess,sys
from pathlib import Path
from lifeos.data_lock import launcher_lock
with launcher_lock(Path(sys.argv[1])):
    child=subprocess.Popen([sys.executable,'-u','-c',sys.argv[3],sys.argv[1],sys.argv[2]],stdout=subprocess.PIPE,text=True)
    assert child.stdout.readline().strip()=='ready'
    print('ready',flush=True)
    sys.stdin.read(1)
"""
    environment = dict(
        os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "services/api")
    )
    stop = tmp_path / "stop-child"
    parent = subprocess.Popen(
        [sys._base_executable, "-u", "-c", parent_code, str(tmp_path), str(stop), child_code],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    try:
        assert parent.stdout.readline().strip() == "ready"
        parent.kill()
        parent.wait(timeout=5)
        with pytest.raises(RuntimeError):
            with data_lock(tmp_path):
                pytest.fail("Orphan runtime must still block recovery")
    finally:
        stop.touch()
        if parent.poll() is None:
            parent.kill()
        parent.communicate(timeout=5)
    deadline = time.monotonic() + 5
    while True:
        try:
            with data_lock(tmp_path):
                break
        except RuntimeError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.02)
