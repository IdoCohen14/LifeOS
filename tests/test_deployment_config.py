import pytest
from lifeos.deployment import DeploymentConfig


def test_local_defaults_remain_loopback_and_http():
    config = DeploymentConfig.from_env({})
    assert config.origin == "http://127.0.0.1:3000"
    assert not config.server and not config.secure_cookies and config.assistant_enabled
    assert config.oauth_callback(3470) == "http://127.0.0.1:3470/api/accounts/oauth/callback"


def server_env(tmp_path, origin="https://LifeOS.Example:443/"):
    return {"LIFEOS_DEPLOYMENT_MODE": "server", "LIFEOS_PUBLIC_ORIGIN": origin,
            "LIFEOS_DATA_DIR": str(tmp_path), "LIFEOS_TEST_MODE": "1"}


def test_server_origin_is_canonical_and_not_request_selected(tmp_path):
    config = DeploymentConfig.from_env(server_env(tmp_path))
    assert config.server and config.secure_cookies and not config.assistant_enabled
    assert config.origin == "https://lifeos.example"
    assert config.oauth_callback(3470) == "https://lifeos.example/api/accounts/oauth/callback"


@pytest.mark.parametrize("origin", ["", "http://lifeos.example", "https://localhost", "https://127.0.0.1",
    "https://user:secret@lifeos.example", "https://lifeos.example/path", "https://lifeos.example?q=x",
    "https://lifeos.example#fragment", " https://lifeos.example", "https://lifeos..example",
    "https://lifeos.local", "https://lifeos.example:0"])
def test_server_rejects_invalid_or_local_origin(tmp_path, origin):
    with pytest.raises(ValueError):
        DeploymentConfig.from_env(server_env(tmp_path, origin))


def test_local_profile_does_not_silently_accept_public_origin():
    with pytest.raises(ValueError):
        DeploymentConfig.from_env({"LIFEOS_PUBLIC_ORIGIN": "https://lifeos.example"})


def test_server_requires_explicit_absolute_data_location(tmp_path):
    env = server_env(tmp_path)
    env["LIFEOS_DATA_DIR"] = "relative-data"
    with pytest.raises(ValueError):
        DeploymentConfig.from_env(env)
