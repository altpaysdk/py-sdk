"""Signing is a wire contract with the server: the canonical string and its HMAC must
match byte-for-byte or the server answers 401 invalid_signature. These tests pin the
exact shape rather than just "some signature comes out"."""

from __future__ import annotations

import base64
import hashlib
import hmac

from altpay.signing import (
    base64url,
    build_canonical_request,
    hmac_sha256,
    new_nonce,
    sha256_hex,
    sign_request,
)

SECRET = "test-secret"


def test_base64url_is_unpadded_urlsafe():
    # The server strips '=' padding and compares the trimmed form. 0xfb 0xff maps to
    # the two url-safe-only characters ('-' and '_'); the standard alphabet would emit
    # '+' and '/' and break header/URL safety.
    assert base64url(b"\xfb\xff") == "-_8"
    assert base64url(b"") == ""
    assert "=" not in base64url(b"any bytes here definitely not a multiple of three!!")


def test_hmac_matches_a_hand_rolled_reference():
    msg = "line1\nline2"
    expected = base64.urlsafe_b64encode(
        hmac.new(SECRET.encode(), msg.encode(), hashlib.sha256).digest()
    ).decode().rstrip("=")
    assert hmac_sha256(SECRET, msg) == expected


def test_canonical_request_field_order_and_separator():
    canonical = build_canonical_request(
        merchant_id="m",
        api_key="k",
        timestamp="1700000000",
        nonce="n",
        body_hash="h",
        method="post",
        path="/api/v2/invoice/create",
    )
    # Order is fixed and the method is upper-cased, query strings never appear here.
    assert canonical == "m\nk\n1700000000\nn\nh\nPOST\n/api/v2/invoice/create"


def test_empty_body_uses_the_canonical_empty_hash():
    headers = sign_request(
        api_secret=SECRET,
        merchant_id="m",
        api_key="k",
        method="POST",
        path="/api/v2/me/get",
        body=b"",
    )
    assert headers["X-Body-Hash"] == hashlib.sha256(b"").hexdigest()


def test_sign_request_is_deterministic_given_fixed_nonce_and_time():
    kwargs = dict(
        api_secret=SECRET,
        merchant_id="m",
        api_key="k",
        method="POST",
        path="/api/v2/invoice/create",
        body=b'{"amount":"1"}',
        timestamp=1700000000,
        nonce="fixed-nonce-value",
    )
    first = sign_request(**kwargs)
    second = sign_request(**kwargs)
    assert first == second

    # And the signature is exactly HMAC over the canonical we can reconstruct.
    expected = hmac_sha256(
        SECRET,
        build_canonical_request(
            merchant_id="m",
            api_key="k",
            timestamp="1700000000",
            nonce="fixed-nonce-value",
            body_hash=sha256_hex(b'{"amount":"1"}'),
            method="POST",
            path="/api/v2/invoice/create",
        ),
    )
    assert first["X-Signature"] == expected


def test_nonce_is_fresh_and_long_enough():
    # The server requires >= 16 chars and rejects reuse inside the TTL so a fresh,
    # unguessable nonce per request is not optional.
    nonces = {new_nonce() for _ in range(200)}
    assert len(nonces) == 200
    assert all(len(n) >= 16 for n in nonces)
