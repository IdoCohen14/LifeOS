from urllib.parse import parse_qs, urlparse

import pytest
from lifeos.account_oauth import AccountOAuth
from lifeos.accounts import AccountService


def test_oauth_is_bound_to_account_session_revision_and_consumed_once(client, setup_app):
    engine = setup_app[0].state.assistant.engine
    accounts = AccountService(engine, enabled=True)
    a = accounts.register("oauth-a", "fixture password a")
    b = accounts.register("oauth-b", "fixture password b")
    sa = accounts.login("oauth-a", "fixture password a")
    sa2 = accounts.login("oauth-a", "fixture password a")
    sb = accounts.login("oauth-b", "fixture password b")
    oauth = AccountOAuth(engine, setup_app[1])
    config = {
        "client_id": "fixture.apps.googleusercontent.com",
        "client_secret": "synthetic-secret",
    }
    oauth.configure(a, "gmail", config)
    url = oauth.start(a, "gmail", sa["token"])
    params = parse_qs(urlparse(url).query)
    assert params["code_challenge_method"] == ["S256"]
    assert params["scope"] == ["https://www.googleapis.com/auth/gmail.readonly"]
    assert "synthetic-secret" not in url
    state = params["state"][0]
    calls = []

    def exchange(values, form, scopes):
        calls.append(form)
        assert form["redirect_uri"] == params["redirect_uri"][0]
        assert len(form["code_verifier"]) >= 43
        return {**values, "access_token": "fixture-access", "refresh_token": "fixture-refresh"}

    with pytest.raises(PermissionError):
        oauth.finish(b, sb["token"], state, "code", exchange=exchange)
    with pytest.raises(PermissionError):
        oauth.finish(a, sa2["token"], state, "code", exchange=exchange)
    assert calls == []
    oauth.finish(a, sa["token"], state, "code", exchange=exchange)
    assert len(calls) == 1
    with pytest.raises(PermissionError):
        oauth.finish(a, sa["token"], state, "code", exchange=exchange)
    state = parse_qs(urlparse(oauth.start(a, "gmail", sa["token"])).query)["state"][0]
    oauth.configure(a, "gmail", config)
    with pytest.raises(PermissionError):
        oauth.finish(a, sa["token"], state, "code", exchange=exchange)
    assert len(calls) == 1
    assert oauth.status(b, "gmail")["configured"] is False
    state = parse_qs(urlparse(oauth.start(a, "gmail", sa["token"])).query)["state"][0]

    def replaced_during_exchange(values, form, scopes):
        oauth.configure(a, "gmail", config)
        return {**values, "access_token": "stale-access", "refresh_token": "stale-refresh"}

    with pytest.raises(RuntimeError):
        oauth.finish(a, sa["token"], state, "code", exchange=replaced_during_exchange)
    lease = oauth.begin_sync(a, "gmail")
    assert "access_token" not in lease["credentials"]
    oauth.abort_sync(a, "gmail", lease["owner"], lease["revision"])
    state = parse_qs(urlparse(oauth.start(a, "gmail", sa["token"])).query)["state"][0]
    accounts.logout(sa["token"])
    with pytest.raises(PermissionError):
        oauth.finish(a, sa["token"], state, "code", exchange=exchange)
