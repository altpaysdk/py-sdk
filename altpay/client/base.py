"""Transport-agnostic request building and response parsing.

The sync and async clients differ only in how they send bytes over the wire. Everything
else (serializing the body, signing it, choosing headers, unwrapping ``result``, turning a
non-2xx status into a typed exception) is identical and lives here.

A :class:`PreparedRequest` is a pure value: given credentials and a call, it produces the
exact method/url/headers/body to send. :func:`parse_response` is a pure function from a raw
response to either the unwrapped ``result`` payload or a raised :class:`~altpay.errors.APIError`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..__meta__ import __user_agent__
from ..credentials import Credentials
from ..errors import error_from_status
from ..signing import sign_request

# The public API is JSON-only and every endpoint is POST (including reads). Bodies are
# serialized compactly and deterministically; the exact bytes are what we hash and sign, so
# the body that goes on the wire must be the body we signed. Never re-serialize downstream.
_JSON_SEPARATORS = (",", ":")


def serialize_body(payload: dict[str, Any] | None) -> bytes:
    """Serialize a request payload to the canonical bytes that get signed and sent.

    ``None`` and ``{}`` both serialize to ``b""``. The body-less endpoints (``me.get``,
    ``invoice/services``) take no body, and the server hashes an empty body for them.
    """
    if not payload:
        return b""
    return json.dumps(payload, separators=_JSON_SEPARATORS, ensure_ascii=False).encode("utf-8")


@dataclass(frozen=True, slots=True)
class PreparedRequest:
    """A fully-signed request ready to hand to httpx."""

    method: str
    url: str
    headers: dict[str, str]
    content: bytes


def prepare(
    *,
    credentials: Credentials,
    base_url: str,
    path: str,
    payload: dict[str, Any] | None,
) -> PreparedRequest:
    """Build and sign a request for ``path`` with ``payload``.

    Args:
        credentials: The merchant credentials to sign with.
        base_url: API root, e.g. ``"https://api.altpay.money"`` (no trailing ``/api/v2``).
        path: The endpoint path, e.g. ``"/api/v2/invoice/create"``.
        payload: The request body as a dict, or ``None`` for body-less endpoints.

    Returns:
        A :class:`PreparedRequest` whose ``headers`` already include the signature set.
    """
    body = serialize_body(payload)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": __user_agent__,
    }
    headers.update(
        sign_request(
            api_secret=credentials.api_secret,
            merchant_id=credentials.merchant_id,
            api_key=credentials.api_key,
            method="POST",
            path=path,
            body=body,
        )
    )
    return PreparedRequest(method="POST", url=f"{base_url}{path}", headers=headers, content=body)


def parse_response(
    *,
    status_code: int,
    body_text: str,
    headers: Any,
) -> Any:
    """Turn a raw response into the unwrapped ``result`` payload, or raise a typed error.

    On a 2xx response, returns the value of the JSON body's ``result`` field (or the whole
    body if it is not wrapped). On any other status, raises the most specific
    :class:`~altpay.errors.APIError` subclass, carrying the server's ``detail`` and the
    ``X-Request-Id`` header (when present) for support correlation.
    """
    parsed = _safe_json(body_text)
    request_id = _get_header(headers, "X-Request-Id")

    if 200 <= status_code < 300:
        if isinstance(parsed, dict) and "result" in parsed:
            return parsed["result"]
        return parsed

    detail = parsed.get("detail") if isinstance(parsed, dict) else None
    retry_after = _parse_retry_after(_get_header(headers, "Retry-After"))
    raise error_from_status(
        status_code,
        detail=detail if isinstance(detail, str) else None,
        response_body=parsed,
        request_id=request_id,
        retry_after=retry_after,
    )


def _safe_json(text: str) -> Any:
    """Parse JSON, falling back to the raw text so a non-JSON error page is still surfaced."""
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return text


def _get_header(headers: Any, name: str) -> str | None:
    """Read a header from an httpx.Headers (case-insensitive) or a plain mapping."""
    try:
        return headers.get(name)
    except AttributeError:
        lowered = name.lower()
        for key, value in dict(headers).items():
            if str(key).lower() == lowered:
                return value
        return None


def _parse_retry_after(value: str | None) -> float | None:
    """Parse a ``Retry-After`` header expressed in seconds; ignore HTTP-date form."""
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None
