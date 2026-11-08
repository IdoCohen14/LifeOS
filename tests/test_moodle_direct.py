import base64
import hashlib
from urllib.parse import parse_qs

import httpx
import pytest
from lifeos.moodle_direct import ORIGIN, MoodleDirectClient, callback_token, launch_url

PASSPORT = "a" * 48
TOKEN = "b" * 32


def callback(passport=PASSPORT):
    tag = hashlib.md5((ORIGIN + passport).encode(), usedforsecurity=False).hexdigest()
    return "lifeosmoodle://token=" + base64.b64encode((tag + ":::" + TOKEN).encode()).decode()


def test_callback_bound_to_own_site_and_one_login_state():
    assert callback_token(callback(), PASSPORT) == TOKEN
    assert callback_token(callback() + "/", PASSPORT) == TOKEN
    assert "service=moodle_mobile_app" in launch_url(PASSPORT)
    assert "confirmed=1" in launch_url(PASSPORT)
    for bad in (callback("c" * 48), "https://elsewhere/token=x", "lifeosmoodle://token=bad"):
        with pytest.raises(ValueError, match="Invalid login response"):
            callback_token(bad, PASSPORT)


def test_courses_use_only_authenticated_read_functions_and_minimize_fields():
    calls = []

    def handler(request):
        assert request.url == ORIGIN + "/webservice/rest/server.php"
        assert "wstoken" not in request.url.query.decode()
        body = parse_qs(request.content.decode())
        assert body["wstoken"] == [TOKEN]
        function = body["wsfunction"][0]
        calls.append(function)
        if function == "core_webservice_get_site_info":
            return httpx.Response(200, json={"siteurl": ORIGIN, "userid": 7,
                "functions": [{"name": "core_enrol_get_users_courses"}]})
        assert body["userid"] == ["7"]
        return httpx.Response(200, json=[{"id": 9, "fullname": "Fixture course",
            "shortname": "F", "startdate": 0, "summary": "not retained"}])

    client = MoodleDirectClient(TOKEN, transport=httpx.MockTransport(handler))
    assert client.courses() == [{"id": 9, "name": "Fixture course", "shortname": "F", "startdate": 0}]
    assert len(calls) == 2
    with pytest.raises(ValueError, match="not allowed"):
        client.read("core_course_delete_courses")


@pytest.mark.parametrize("response", [
    httpx.Response(302, headers={"location": "https://elsewhere"}),
    httpx.Response(200, json={"exception": "error", "message": TOKEN}),
    httpx.Response(200, content=b"x" * (2 * 1024 * 1024 + 1)),
])
def test_network_errors_are_bounded_and_never_echo_tokens(response):
    client = MoodleDirectClient(TOKEN, transport=httpx.MockTransport(lambda r: response))
    with pytest.raises(ValueError) as error:
        client.read("core_webservice_get_site_info")
    assert TOKEN not in str(error.value)


def test_native_proof_consumes_state_and_retains_no_token(tmp_path, monkeypatch):
    import importlib.util
    import json
    import time
    from pathlib import Path
    from uuid import uuid4

    from lifeos.credential_vault import CredentialVault

    source = Path(__file__).resolve().parents[1] / "scripts/probe_moodle_courses.py"
    spec = importlib.util.spec_from_file_location("native_moodle_proof", source)
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    owner = str(uuid4())
    monkeypatch.setattr(tool, "context", lambda: (tmp_path, owner))
    monkeypatch.setattr(tool.MoodleDirectClient, "courses", lambda self: [{"id": 9, "name": "Fixture"}])
    folder = tool.proof_folder(tmp_path, owner)
    vault = CredentialVault(tmp_path)
    pending = folder / "moodle-direct-pending.bin"
    pending.write_bytes(vault.encrypt({"account_id": owner, "passport": PASSPORT, "expires": int(time.time()) + 60}))
    assert tool.receive(callback())["course_count"] == 1
    assert not pending.exists()
    report = vault.decrypt((folder / "moodle-direct-discovery.bin").read_bytes())
    assert TOKEN not in json.dumps(report)
    assert report["account_id"] == owner
    with pytest.raises(ValueError, match="No pending"):
        tool.receive(callback())
    pending.write_bytes(vault.encrypt({"account_id": owner, "passport": PASSPORT, "expires": 1}))
    with pytest.raises(ValueError, match="expired"):
        tool.receive(callback())
    assert not pending.exists()
