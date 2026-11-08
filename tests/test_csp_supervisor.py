import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_invalid_web_build_is_rejected_before_api_web_or_worker_starts(monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
    import supervise

    monkeypatch.setattr(sys, 'argv', ['supervise.py', '--parent-pid', '123'])
    monkeypatch.setattr(supervise, 'ParentProcess', lambda _: SimpleNamespace(alive=lambda: True, close=lambda: None))
    monkeypatch.setattr(supervise, 'constrain_service_tree', lambda: None)
    def refuse(command, **kwargs):
        assert command[-1].endswith('verify-build.mjs')
        raise subprocess.CalledProcessError(1, command)
    monkeypatch.setattr(supervise.subprocess, 'run', refuse)
    monkeypatch.setattr(supervise.subprocess, 'Popen', lambda *a, **k: pytest.fail('service started before CSP preflight'))
    with pytest.raises(subprocess.CalledProcessError):
        supervise.main()
