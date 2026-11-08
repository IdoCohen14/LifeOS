import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from process_tree import ParentProcess  # noqa: E402


def test_posix_cleanup_escalates_groups_even_after_direct_child_exits(monkeypatch):
    from types import SimpleNamespace

    import supervise

    calls = []
    monkeypatch.setattr(
        supervise,
        "os",
        SimpleNamespace(name="posix", killpg=lambda pid, sig: calls.append((pid, sig))),
    )
    monkeypatch.setattr(supervise, "signal", SimpleNamespace(SIGTERM=15, SIGKILL=9))
    child = SimpleNamespace(pid=123, wait=lambda timeout: 0)
    supervise.stop_children([child])
    assert calls == [(123, 15), (123, 9)]


def test_cleanup_uses_one_shared_deadline(monkeypatch):
    from types import SimpleNamespace

    import supervise

    tick = [0.0]
    waits = []
    monkeypatch.setattr(supervise, "os", SimpleNamespace(name="posix", killpg=lambda *args: None))
    monkeypatch.setattr(supervise, "signal", SimpleNamespace(SIGTERM=15, SIGKILL=9))
    monkeypatch.setattr(supervise, "time", SimpleNamespace(monotonic=lambda: tick[0]))

    def wait(timeout):
        waits.append(timeout)
        tick[0] += timeout
        raise subprocess.TimeoutExpired("fixture", timeout)

    supervise.stop_children([SimpleNamespace(pid=index, wait=wait) for index in range(100, 103)])
    assert sum(waits) <= 4


@pytest.mark.skipif(os.name != "nt", reason="Windows job-object behavior")
@pytest.mark.parametrize("exit_mode", ["normal", "killed"])
def test_job_closes_child_and_grandchild_when_supervisor_exits(tmp_path, exit_mode):
    child_code = """
import subprocess,sys,time
grandchild=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])
print(grandchild.pid,flush=True)
time.sleep(60)
"""
    parent_code = """
import json,subprocess,sys
from process_tree import constrain_service_tree
job=constrain_service_tree()
child=subprocess.Popen([sys.executable,'-u','-c',sys.argv[1]],stdout=subprocess.PIPE,text=True)
grandchild=int(child.stdout.readline())
print(json.dumps([child.pid,grandchild]),flush=True)
sys.stdin.read(1)
"""
    parent = subprocess.Popen(
        [sys._base_executable, "-u", "-c", parent_code, child_code],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=dict(os.environ, PYTHONPATH=str(SCRIPTS)),
    )
    handles = []
    try:
        line = parent.stdout.readline()
        assert line, parent.stderr.read()
        handles = [ParentProcess(pid) for pid in json.loads(line)]
        assert all(handle.alive() for handle in handles)
        if exit_mode == "normal":
            parent.communicate("x", timeout=5)
            assert parent.returncode == 0
        else:
            parent.kill()
            parent.wait(timeout=5)
        deadline = time.monotonic() + 5
        while any(handle.alive() for handle in handles) and time.monotonic() < deadline:
            time.sleep(0.02)
        assert all(not handle.alive() for handle in handles)
    finally:
        if parent.poll() is None:
            parent.kill()
        parent.communicate(timeout=5)
        for handle in handles:
            handle.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows launcher crash acceptance")
@pytest.mark.parametrize("failure", ["launcher", "supervisor", "api"])
def test_launcher_crash_closes_fixture_services_and_releases_recovery_guard(tmp_path, failure):
    root = SCRIPTS.parent
    if not tmp_path.resolve().is_relative_to(root / ".runtime"):
        pytest.skip("Lifecycle acceptance requires .runtime temp data")
    build = ".next-recovery"
    if not (root / "apps/web" / build / "BUILD_ID").exists():
        pytest.skip("Build isolated web release before lifecycle acceptance")
    # A harness job owns every fixture process, so a failed assertion cannot orphan them.
    harness = r"""
import ctypes,json,os,socket,subprocess,sys,time,urllib.request
from ctypes import wintypes
from pathlib import Path
from process_tree import constrain_service_tree
sys.path.insert(0,str(Path.cwd()/'services/api'))
from lifeos.data_lock import data_lock
job=constrain_service_tree()
directory=Path(sys.argv[1]);build=sys.argv[2];failure=sys.argv[3]
def record(stage, **values):
    with (directory/'harness-stages.jsonl').open('a',encoding='utf-8') as diagnostics:
        diagnostics.write(json.dumps(dict(stage=stage,harness_pid=os.getpid(),**values))+'\n')
record('started',failure=failure)
ports=[]
for _ in range(2):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));ports.append(sock.getsockname()[1])
assert ports[0]!=ports[1]
def listening(port):
    with socket.socket() as sock:
        sock.settimeout(.1);return sock.connect_ex(('127.0.0.1',port))==0
with (directory/'launcher.log').open('w',encoding='utf-8') as log:
    launcher=subprocess.Popen([str(Path.cwd()/'.venv/Scripts/python.exe'),'scripts/run.py',
        '--no-browser','--test-mode','--data-dir',str(directory),'--build-dir',build,
        '--web-port',str(ports[0]),'--api-port',str(ports[1])],stdout=log,stderr=log,
        env=dict(os.environ,LIFEOS_SETUP_PASSWORD='synthetic lifecycle password'),
        creationflags=subprocess.CREATE_NO_WINDOW)
    deadline=time.monotonic()+20
    while not all(listening(p) for p in ports):
        assert launcher.poll() is None,'fixture launcher exited'
        assert time.monotonic()<deadline,'fixture services not ready'
        time.sleep(.05)
    record('services_ready',launcher_pid=launcher.pid,ports=ports)
    command=f"Get-CimInstance Win32_Process -Filter 'ParentProcessId = {launcher.pid}' | Where-Object Name -eq python.exe | Select-Object -ExpandProperty ProcessId"
    actual=int(subprocess.check_output(['powershell.exe','-NoProfile','-Command',command],text=True).strip())
    if failure=='supervisor':
        for _ in range(2):
            command=f"Get-CimInstance Win32_Process -Filter 'ParentProcessId = {actual}' | Where-Object Name -eq python.exe | Select-Object -ExpandProperty ProcessId"
            actual=int(subprocess.check_output(['powershell.exe','-NoProfile','-Command',command],text=True).strip())
    elif failure=='api':
        command=f"Get-NetTCPConnection -LocalPort {ports[1]} -State Listen | Select-Object -ExpandProperty OwningProcess -Unique"
        actual=int(subprocess.check_output(['powershell.exe','-NoProfile','-Command',command],text=True).strip())
    record('target_selected',target_pid=actual,launcher_pid=launcher.pid,ports=ports)
    assert actual not in {os.getpid(),os.getppid()},'fixture target is harness or pytest'
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.TerminateProcess.argtypes=[wintypes.HANDLE,wintypes.UINT]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.OpenProcess(0x00100001,False,actual)
    assert handle
    try: assert kernel.TerminateProcess(handle,1)
    finally: kernel.CloseHandle(handle)
    record('target_terminated',target_pid=actual)
    launcher.wait(timeout=5)
    record('launcher_exited',returncode=launcher.returncode)
    deadline=time.monotonic()+5
    while any(listening(p) for p in ports) and time.monotonic()<deadline:time.sleep(.02)
    assert not any(listening(p) for p in ports),'orphan fixture ports remain open'
    deadline=time.monotonic()+5
    while True:
        try:
            with data_lock(directory):break
        except RuntimeError:
            if time.monotonic()>=deadline:raise
            time.sleep(.02)
record('cleanup_verified')
print('fixture crash cleanup passed')
"""
    parent = subprocess.Popen(
        [sys.executable, "-u", "-c", harness, str(tmp_path), build, failure],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=root,
        env=dict(os.environ, PYTHONPATH=str(SCRIPTS)),
    )
    try:
        out, err = parent.communicate(timeout=40)
        diagnostics = tmp_path / "harness-stages.jsonl"
        stages = diagnostics.read_text(encoding="utf-8") if diagnostics.exists() else "no stages"
        assert parent.returncode == 0, f"harness exit={parent.returncode}\n{out}{err}\n{stages}"
        assert "fixture crash cleanup passed" in out
    finally:
        if parent.poll() is None:
            parent.kill()
        parent.communicate(timeout=5)
