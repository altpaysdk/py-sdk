"""Request signing and webhook verification primitives.

Every call to the AltPay public API is authenticated with a per-request HMAC-SHA256
signature; every webhook AltPay delivers carries one too. Both use the same hashing
primitives but a different canonical string, so they live together here.

The canonical strings below are byte-for-byte identical to the server. Any divergence
(field order, separator, body hashing, padding) produces a valid-looking signature that
the server rejects with ``invalid_signature``, so treat this module as a contract: change
it only alongside the backend.

See https://docs.altpay.money/docs/authentication for the full specification.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time

# SHA-256 of an empty byte string, reused for every body-less request so we never re-hash
# ``b""``. Matches ``sha256_hex(b"")`` on the server.
_EMPTY_BODY_HASH = hashlib.sha256(b"").hexdigest()


def base64url(raw: bytes) -> str:
    """Encode bytes as unpadded base64url.

    The server strips ``=`` padding from signatures and compares the trimmed form, so the
    SDK must produce the same. Padding is purely positional, so dropping it loses no
    information and keeps the value URL/header safe.
    """
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def hmac_sha256(secret: str, message: str) -> str:
    """Return the unpadded base64url HMAC-SHA256 of ``message`` keyed by ``secret``."""
    digest = hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).digest()
    return base64url(digest)


def sha256_hex(data: bytes) -> str:
    """Return the lowercase hex SHA-256 of ``data`` (the body-hash format the API expects)."""
    return hashlib.sha256(data).hexdigest()


def new_nonce() -> str:
    """Generate a fresh request nonce.

    The server requires at least 16 characters and rejects any nonce reused inside the
    signature TTL (replay protection), so we mint a 32-byte url-safe token per request.
    """
    return secrets.token_urlsafe(32)


def build_canonical_request(
    *,
    merchant_id: str,
    api_key: str,
    timestamp: str,
    nonce: str,
    body_hash: str,
    method: str,
    path: str,
) -> str:
    """Assemble the canonical string the request signature is computed over.

    The fields are joined with a single newline in this exact order::

        merchant_id\\n api_key\\n timestamp\\n nonce\\n body_hash\\n METHOD\\n path

    ``path`` is the URL path only. The query string is excluded (it is not used by the
    public API). ``method`` is upper-cased. ``body_hash`` is the lowercase hex SHA-256 of
    the raw request body (``sha256_hex(b"")`` for body-less requests).
    """
    return "\n".join([merchant_id, api_key, timestamp, nonce, body_hash, method.upper(), path])


def sign_request(
    *,
    api_secret: str,
    merchant_id: str,
    api_key: str,
    method: str,
    path: str,
    body: bytes,
    timestamp: int | None = None,
    nonce: str | None = None,
) -> dict[str, str]:
    """Compute the full set of signature headers for one outgoing request.

    Args:
        api_secret: The signing secret bound to ``api_key`` (never sent over the wire).
        merchant_id: The merchant UUID (sent as ``X-Merchant-Id``).
        api_key: The public key identifier (sent as ``X-Api-Key``).
        method: HTTP method, e.g. ``"POST"``.
        path: URL path, e.g. ``"/api/v2/invoice/create"`` (no query string).
        body: The exact request body bytes that will be transmitted.
        timestamp: Override the Unix timestamp (seconds). Defaults to ``time.time()``.
            Pass a fixed value only for tests; the server rejects timestamps older than
            its TTL or more than 30 seconds in the future.
        nonce: Override the request nonce. Defaults to a fresh :func:`new_nonce`.

    Returns:
        A mapping of header name to value: ``X-Merchant-Id``, ``X-Api-Key``,
        ``X-Timestamp``, ``X-Nonce``, ``X-Body-Hash`` and ``X-Signature``.
    """
    ts = str(int(time.time()) if timestamp is None else timestamp)
    nce = nonce or new_nonce()
    body_hash = _EMPTY_BODY_HASH if not body else sha256_hex(body)
    canonical = build_canonical_request(
        merchant_id=merchant_id,
        api_key=api_key,
        timestamp=ts,
        nonce=nce,
        body_hash=body_hash,
        method=method,
        path=path,
    )
    return {
        "X-Merchant-Id": merchant_id,
        "X-Api-Key": api_key,
        "X-Timestamp": ts,
        "X-Nonce": nce,
        "X-Body-Hash": body_hash,
        "X-Signature": hmac_sha256(api_secret, canonical),
    }


def build_canonical_webhook(
    *,
    webhook_id: str,
    timestamp: str,
    nonce: str,
    body_hash: str,
    target: str,
) -> str:
    """Assemble the canonical string an incoming webhook signature is computed over.

    This differs from the request canonical: it has no merchant_id/api_key, the method
    is always ``POST``, and ``target`` is the full request-target (``path[;params][?query]``)
    rather than path-only. Fields are newline-joined::

        webhook_id\\n timestamp\\n nonce\\n body_hash\\n POST\\n target
    """
    return "\n".join([webhook_id, timestamp, nonce, body_hash, "POST", target])


def verify_webhook(
    *,
    secret: str,
    body: bytes,
    headers: dict[str, str],
    target: str,
    tolerance_seconds: int = 300,
) -> bool:
    """Verify the signature of a webhook AltPay delivered to your endpoint.

    Pass the RAW request body (the exact bytes you received). Do not re-serialize the
    parsed JSON, or the body hash will not match. ``headers`` may be your framework's
    case-insensitive header mapping; the AltPay headers are read by their canonical names
    (``X-Webhook-Id``, ``X-Timestamp``, ``X-Nonce``, ``X-Body-Hash``, ``X-Signature``).

    Args:
        secret: Your webhook secret (distinct from the API signing secret).
        body: The raw request body bytes.
        headers: The incoming request headers.
        target: The request-target the webhook was signed over, the path your endpoint is
            mounted at, including any query string (e.g. ``"/altpay/webhook"`` or
            ``"/hook?token=abc"``). This must match what you configured as ``url_callback``.
        tolerance_seconds: Reject webhooks whose timestamp is older than this (replay
            window). Defaults to 300s. Set to 0 to disable the freshness check.

    Returns:
        ``True`` if the signature, body hash and (optionally) timestamp are all valid.

    The comparison is constant-time. A ``False`` result means the request was not signed by
    your secret, the body was altered in transit, or it is a stale replay. Reject it with
    HTTP 401 and do not act on its contents.

    See https://docs.altpay.money/docs/webhooks for the verification recipe.
    """
    sig = _header(headers, "X-Signature")
    webhook_id = _header(headers, "X-Webhook-Id")
    timestamp = _header(headers, "X-Timestamp")
    nonce = _header(headers, "X-Nonce")
    sent_body_hash = _header(headers, "X-Body-Hash")
    if not sig or not webhook_id or not timestamp or not nonce:
        return False

    body_hash = sha256_hex(body)
    # If the sender included a body hash, it must match the body we actually received,
    # catching tampering before we even check the signature.
    if sent_body_hash and not hmac.compare_digest(body_hash, sent_body_hash.strip().lower()):
        return False

    if tolerance_seconds > 0:
        try:
            age = int(time.time()) - int(timestamp)
        except ValueError:
            return False
        if age > tolerance_seconds or age < -30:
            return False

    canonical = build_canonical_webhook(
        webhook_id=webhook_id,
        timestamp=timestamp,
        nonce=nonce,
        body_hash=body_hash,
        target=target,
    )
    expected = hmac_sha256(secret, canonical)
    return hmac.compare_digest(expected, sig.strip().rstrip("="))


def _header(headers: dict[str, str], name: str) -> str | None:
    """Read a header case-insensitively from a plain dict or a framework header mapping."""
    if name in headers:
        return headers[name]
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return None
