import pytest
from lifeos.accounts import AccountService
from lifeos.web_push import ConfigInput, WebPushService
from lifeos.web_push_delivery import PushDeliveryService
from lifeos.web_push_transport import SubscriptionInput, valid_endpoint
from sqlalchemy.orm import Session
from test_web_push_transport import subscription


@pytest.mark.parametrize("host", ["web.push.apple.com", "region.web.push.apple.com"])
def test_apple_subscription_accepts_only_documented_service_namespace(host):
    assert SubscriptionInput.model_validate(subscription(f"https://{host}/fixture-token_12345"))


@pytest.mark.parametrize("endpoint", ["https://web.push.apple.com.evil.test/fixture-token_12345",
    "https://evilpush.apple.com/fixture-token_12345", "https://push.apple.com/fixture-token_12345",
    "http://web.push.apple.com/fixture-token_12345", "https://web.push.apple.com:444/fixture-token_12345",
    "https://web.push.apple.com/fixture-token_12345?x=1", "https://user@web.push.apple.com/fixture-token_12345",
    "https://" + "a." * 130 + "push.apple.com/fixture-token_12345"])
def test_apple_subscription_rejects_spoofed_or_unsupported_destinations(endpoint):
    with pytest.raises(ValueError):
        valid_endpoint(endpoint)


def test_apple_vapid_is_encrypted_persistent_owned_and_reused_for_multiple_sends(client, setup_app, monkeypatch):
    import time

    from lifeos import web_push_delivery

    engine, directory = setup_app[0].state.assistant.engine, setup_app[1]
    auth = AccountService(engine, enabled=True)
    owner = auth.register("apple-owner", "fixture password")
    other = auth.register("apple-other", "fixture password")
    service = WebPushService(engine, directory, account_id=owner)
    service.configure(ConfigInput(contact="fixture@example.test", revision=0))
    with Session(engine) as db:
        key = service.open(db.get(service.models[0], owner).private_key)["key"]
    audience = "https://web.push.apple.com"
    first = service.apple_vapid_headers(key, "fixture@example.test", audience)
    recreated = WebPushService(engine, directory, account_id=owner)
    assert recreated.apple_vapid_headers(key, "fixture@example.test", audience) == first
    with Session(engine) as db:
        cipher = db.get(service.models[0], owner).private_key
        assert first["Authorization"].encode() not in cipher
        assert service.open(cipher)["apple_vapid"][audience]["headers"] == first
    observed = []
    monkeypatch.setattr(web_push_delivery, "send_push", lambda *args, **kwargs: observed.append(kwargs["vapid_headers"]) or (201, 300))
    delivery = PushDeliveryService(engine, directory, account_id=owner)
    for _ in range(2):
        assert delivery.send_default(subscription(audience + "/fixture-token_12345"), key,
                                     "fixture@example.test", {"id": "generic-fixture"})[0] == 201
    assert observed == [first, first]
    foreign = WebPushService(engine, directory, account_id=other)
    foreign.configure(ConfigInput(contact="fixture@example.test", revision=0))
    with pytest.raises(ValueError, match="config_changed"):
        foreign.apple_vapid_headers(key, "fixture@example.test", audience)
    with pytest.raises(ValueError, match="config_changed"):
        service.apple_vapid_headers(key, "changed@example.test", audience)
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now + 12 * 60 * 60)
    assert service.apple_vapid_headers(key, "fixture@example.test", audience) != first


def test_apple_transport_uses_cached_vapid_and_encrypted_payload_without_network(client, setup_app):
    import json
    import time

    import http_ece
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from lifeos.web_push_transport import send_push
    from test_web_push_transport import encoded

    engine, directory = setup_app[0].state.assistant.engine, setup_app[1]
    owner = AccountService(engine, enabled=True).register("apple-transport", "fixture password")
    service = WebPushService(engine, directory, account_id=owner)
    service.configure(ConfigInput(contact="fixture@example.test", revision=0))
    with Session(engine) as db:
        key = service.open(db.get(service.models[0], owner).private_key)["key"]
    headers = service.apple_vapid_headers(key, "fixture@example.test", "https://web.push.apple.com")
    value = subscription("https://web.push.apple.com/fixture-token_12345")
    receiver = ec.generate_private_key(ec.SECP256R1())
    value["keys"]["p256dh"] = encoded(receiver.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
    payload = {"id": "a" * 64, "language": "en", "zone": "Asia/Jerusalem", "quiet_enabled": False,
               "quiet_start": "22:00", "quiet_end": "07:00", "expires": int(time.time()) + 300}
    class Response:
        status = 201
        text = ""
        def getheader(self, name, default=""): return default
        def read(self, *args): pytest.fail("Provider body must not be read")
        def close(self): pass
    class Connection:
        def __init__(self, host, **kwargs):
            assert host == "web.push.apple.com" and kwargs["port"] == 443
            assert kwargs["context"].check_hostname
        def set_debuglevel(self, value): assert value == 0
        def request(self, method, path, *, body, headers):
            assert method == "POST" and path == "/fixture-token_12345"
            assert b"generic-fixture" not in body
            assert headers["Authorization"] == cached["Authorization"]
            assert headers["TTL"] == "0"
            opened = json.loads(http_ece.decrypt(body, private_key=receiver,
                auth_secret=b"0123456789abcdef", version="aes128gcm"))
            assert opened == {**payload, "visible_required": True}
        def getresponse(self): return Response()
        def close(self): pass
    cached = headers
    assert send_push(value, key, "fixture@example.test", payload,
                     connection_factory=Connection, vapid_headers=headers)[0] == 201
    with pytest.raises(ValueError, match="cache_required"):
        send_push(value, key, "fixture@example.test", {}, connection_factory=Connection)
