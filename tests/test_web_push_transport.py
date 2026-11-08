import base64

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def encoded(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def subscription(endpoint="https://fcm.googleapis.com/fcm/send/fixture-token-12345"):
    key = ec.generate_private_key(ec.SECP256R1())
    return {
        "endpoint": endpoint,
        "keys": {
            "p256dh": encoded(
                key.public_key().public_bytes(
                    serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
                )
            ),
            "auth": encoded(b"0123456789abcdef"),
        },
        "expirationTime": None,
    }


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://fcm.googleapis.com/fcm/send/fixture-token-12345",
        "https://fcm.googleapis.com.evil.test/fcm/send/fixture-token-12345",
        "https://127.0.0.1/fcm/send/fixture-token-12345",
        "https://fcm.googleapis.com:444/fcm/send/fixture-token-12345",
        "https://user@fcm.googleapis.com/fcm/send/fixture-token-12345",
        "https://fcm.googleapis.com/fcm/send/fixture-token-12345?secret=value",
        "https://fcm.googleapis.com/fcm/send/fixture-token-12345#x",
        "https://fcm.googleapis.com/other/fixture-token-12345",
    ],
)
def test_push_subscription_rejects_untrusted_endpoint(endpoint):
    from lifeos.web_push_transport import SubscriptionInput

    with pytest.raises(ValueError):
        SubscriptionInput.model_validate(subscription(endpoint))


def test_push_accepts_supported_keys_but_rejects_bad_point_and_auth():
    from lifeos.web_push_transport import SubscriptionInput

    for hostpath in [
        "fcm.googleapis.com/wp/fixture-token-12345",
        "updates.push.services.mozilla.com/wpush/v2/fixture-token-12345",
    ]:
        assert SubscriptionInput.model_validate(subscription("https://" + hostpath))
    body = subscription()
    body["keys"]["p256dh"] = encoded(b"\x04" + b"\x00" * 64)
    with pytest.raises(ValueError):
        SubscriptionInput.model_validate(body)
    body = subscription()
    body["keys"]["auth"] = encoded(b"short")
    with pytest.raises(ValueError):
        SubscriptionInput.model_validate(body)


def test_web_push_encrypts_for_receiver_and_never_reads_or_follows_remote_body(caplog):
    import logging

    import http_ece
    from lifeos.web_push_transport import send_push

    caplog.set_level(logging.DEBUG)
    receiver = ec.generate_private_key(ec.SECP256R1())
    value = subscription()
    value["keys"]["p256dh"] = encoded(
        receiver.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
    )
    private = ec.generate_private_key(ec.SECP256R1())
    signing = encoded(
        private.private_bytes(
            serialization.Encoding.DER,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    observed = []
    codes = [201, 307]

    class Response:
        status = 201

        def read(self, *args):
            pytest.fail("Push provider body must never be read")

        def getheader(self, name, default=""):
            return "http://127.0.0.1/private" if name == "location" else default

        def close(self):
            pass

    class Connection:
        def __init__(self, host, **kwargs):
            assert host == "fcm.googleapis.com" and kwargs["timeout"] == 10
            self.response = Response()
            self.response.status = codes.pop(0)

        def set_debuglevel(self, value):
            assert value == 0

        def request(self, method, path, *, body, headers):
            assert method == "POST" and path.startswith("/fcm/send/")
            observed.append(body)
            assert b"fixture-notice" not in body
            assert b"fixture-notice" in http_ece.decrypt(
                body, private_key=receiver, auth_secret=b"0123456789abcdef", version="aes128gcm"
            )
            assert headers["TTL"] == "300" and headers["Authorization"].startswith("vapid ")

        def getresponse(self):
            return self.response

        def close(self):
            pass

    assert (
        send_push(
            value,
            signing,
            "fixture@example.test",
            {"id": "fixture-notice"},
            connection_factory=Connection,
        )[0]
        == 201
    )
    assert (
        send_push(
            value,
            signing,
            "fixture@example.test",
            {"id": "fixture-notice"},
            connection_factory=Connection,
        )[0]
        == 307
    )
    assert len(observed) == 2
    assert "fixture-token-12345" not in caplog.text and signing not in caplog.text
