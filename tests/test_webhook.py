"""A webhook verifier that accepts a forged event is worse than none: it hands an
attacker order fulfilment. These tests sign a real event the way the server does, then
check that every mutation (body, timestamp, signature, missing header) is rejected."""

from __future__ import annotations

import time

import pytest

from altpay import AuthenticationError, WebhookVerifier
from altpay.enums import PaymentStatus
from altpay.signing import build_canonical_webhook, hmac_sha256, sha256_hex

SECRET = "whsec_test"
TARGET = "/altpay/webhook"
BODY = b'{"event":"payment.updated","payment_id":"p1","external_id":"o1","status":"paid"}'


def _headers(body: bytes = BODY, *, timestamp: int | None = None, secret: str = SECRET):
    ts = str(int(time.time()) if timestamp is None else timestamp)
    body_hash = sha256_hex(body)
    canonical = build_canonical_webhook(
        webhook_id="wh_1", timestamp=ts, nonce="nonce-1", body_hash=body_hash, target=TARGET
    )
    return {
        "X-Webhook-Id": "wh_1",
        "X-Timestamp": ts,
        "X-Nonce": "nonce-1",
        "X-Body-Hash": body_hash,
        "X-Signature": hmac_sha256(secret, canonical),
    }


def test_verify_accepts_a_correctly_signed_event():
    v = WebhookVerifier(SECRET, target=TARGET)
    assert v.verify(BODY, _headers()) is True


def test_parse_decodes_into_a_typed_event():
    v = WebhookVerifier(SECRET, target=TARGET)
    event = v.parse(BODY, _headers())
    assert event.status is PaymentStatus.PAID
    assert event.payment_id == "p1"


def test_tampered_body_is_rejected():
    # Signature was computed over the original body; a changed body must not verify.
    v = WebhookVerifier(SECRET, target=TARGET)
    forged = BODY.replace(b'"paid"', b'"failed"')
    assert v.verify(forged, _headers()) is False


def test_wrong_secret_is_rejected():
    v = WebhookVerifier(SECRET, target=TARGET)
    assert v.verify(BODY, _headers(secret="not-the-secret")) is False


def test_stale_event_is_rejected_and_zero_tolerance_disables_the_check():
    old = int(time.time()) - 3600
    assert WebhookVerifier(SECRET, target=TARGET).verify(BODY, _headers(timestamp=old)) is False
    assert WebhookVerifier(SECRET, target=TARGET, tolerance_seconds=0).verify(
        BODY, _headers(timestamp=old)
    ) is True


def test_missing_signature_header_is_rejected():
    headers = _headers()
    del headers["X-Signature"]
    assert WebhookVerifier(SECRET, target=TARGET).verify(BODY, headers) is False


def test_headers_are_read_case_insensitively():
    # Frameworks lower-case incoming headers; the verifier must still find them.
    lowered = {k.lower(): val for k, val in _headers().items()}
    assert WebhookVerifier(SECRET, target=TARGET).verify(BODY, lowered) is True


def test_parse_raises_authentication_error_on_a_bad_signature():
    v = WebhookVerifier(SECRET, target=TARGET)
    with pytest.raises(AuthenticationError):
        v.parse(BODY, _headers(secret="wrong"))


def test_empty_secret_is_refused_at_construction():
    with pytest.raises(ValueError):
        WebhookVerifier("", target=TARGET)
