"""Exception hierarchy for the AltPay SDK.

Every failure raised by a client is an :class:`AltPayError`. Transport problems (timeouts,
connection resets) raise :class:`AltPayTransportError`; anything the API answered with a
non-2xx status raises an :class:`APIError` subclass chosen by HTTP status. The API reports
its own machine-readable reason in the JSON body's ``detail`` field (for example
``"invalid_signature"``, ``"invoice_not_found"``). That string is preserved on
:attr:`APIError.detail` and drives the human-readable hint each exception carries.

The exception you catch tells you the category; ``detail`` tells you the specific reason;
the docstring and :attr:`APIError.hint` tell you how to fix it. The full catalogue,
including every ``detail`` value, lives at https://docs.altpay.money/docs/http-codes.
"""

from __future__ import annotations

DOCS_ERRORS_URL = "https://docs.altpay.money/docs/http-codes"


class AltPayError(Exception):
    """Base class for every error raised by the SDK. Catch this to handle all SDK failures."""


class AltPayTransportError(AltPayError):
    """The request never produced an HTTP response.

    Raised on connection failures, DNS errors, TLS errors and timeouts: the network, not
    the API, is the problem. These are usually transient. Retry with backoff, check
    connectivity and that ``base_url`` is reachable. The original exception is chained as
    ``__cause__``.

    See https://docs.altpay.money/docs/http-codes#transport
    """


class APIError(AltPayError):
    """The API returned a non-2xx response.

    Attributes:
        status_code: The HTTP status code.
        detail: The machine-readable reason from the response body's ``detail`` field, or
            ``None`` if the body had no such field.
        hint: A short, human-readable explanation of the likely cause and fix.
        response_body: The parsed JSON body (or raw text) for inspection.
        request_id: The value of the response ``X-Request-Id`` header, if present. Quote it
            in support requests.
    """

    #: Default hint used when a subclass does not refine it per ``detail``.
    default_hint = "The API rejected the request. See the docs for this error category."

    def __init__(
        self,
        status_code: int,
        *,
        detail: str | None = None,
        response_body: object = None,
        request_id: str | None = None,
        hint: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.detail = detail
        self.response_body = response_body
        self.request_id = request_id
        self.hint = hint or _HINTS.get(detail or "", self.default_hint)
        message = f"HTTP {status_code}"
        if detail:
            message += f" ({detail})"
        message += f": {self.hint} -> {DOCS_ERRORS_URL}"
        if request_id:
            message += f" [request_id={request_id}]"
        super().__init__(message)


class AuthenticationError(APIError):
    """HTTP 401, the request signature was rejected (``detail="invalid_signature"``).

    This single status covers every signing problem so an attacker cannot tell which check
    failed. Common causes:

    * Wrong ``api_secret``, ``api_key`` or ``merchant_id`` (most common: re-check the three
      credentials match one active key issued in your dashboard).
    * Clock skew: your ``X-Timestamp`` is outside the server's window. The SDK uses
      ``time.time()``; make sure the host clock is synced (NTP).
    * A reused nonce (replay), only an issue if you sign requests yourself or retry with a
      frozen nonce. Let the SDK mint a fresh one per attempt.
    * The signing canonical does not match (custom signing only). Prefer the SDK's
      :func:`altpay.signing.sign_request` over hand-rolling it.
    * The API key was revoked or deactivated.

    See https://docs.altpay.money/docs/http-codes#authentication
    """

    default_hint = (
        "Signature rejected. Verify api_key/api_secret/merchant_id, that your clock is "
        "NTP-synced, and that the key is active."
    )


class PermissionError_(APIError):
    """HTTP 403, authenticated but not allowed to perform this action.

    Common ``detail`` values:

    * ``ip_not_allowed``: your server IP is not in the key's IP allowlist. Add it in the
      dashboard or disable the allowlist.
    * ``ip_blocked``: the IP was blocked for abuse; contact support.
    * a merchant-approval message: your merchant account is not approved yet, so it cannot
      create invoices. Finish onboarding first.

    Named with a trailing underscore to avoid shadowing the builtin ``PermissionError``;
    exported as ``Forbidden``.

    See https://docs.altpay.money/docs/http-codes#forbidden
    """

    default_hint = "Forbidden: IP allowlist, an IP block, or an unapproved merchant account."


class NotFoundError(APIError):
    """HTTP 404, the referenced resource does not exist for your merchant.

    Typically ``detail="invoice_not_found"``: the ``uuid``/``order_id`` you queried has no
    matching invoice under this merchant. Confirm you are using the right identifier (the
    ``uuid`` you supplied at creation, or the ``order_id`` the API returned) and the right
    credentials.

    See https://docs.altpay.money/docs/http-codes#not-found
    """

    default_hint = "Resource not found for this merchant. Check the identifier and credentials."


class ValidationError(APIError):
    """HTTP 400/422, the request body failed validation (``detail="invalid_request"``).

    A field is missing, has the wrong type, or violates a constraint (``amount`` not greater
    than zero, ``lifetime`` outside 60-1440, a malformed callback URL). When you use the
    typed request models the SDK validates locally first, so most of these are caught before
    the request leaves your process.

    See https://docs.altpay.money/docs/http-codes#validation
    """

    default_hint = "Request validation failed. Check required fields, types and constraints."


class ConflictError(APIError):
    """HTTP 409, the request conflicts with the resource's current state.

    Examples: a payment method is already locked for an invoice, the invoice is already
    paid, or it is no longer payable. These are state errors, not retryable as-is. Fetch
    the current invoice state and act on it.

    See https://docs.altpay.money/docs/http-codes#conflict
    """

    default_hint = "State conflict. Re-read the resource state; the action no longer applies."


class RateLimitError(APIError):
    """HTTP 429, too many requests (``detail="rate_limited"``).

    Attributes:
        retry_after: Seconds to wait before retrying, parsed from the ``Retry-After``
            response header, or ``None`` if absent.

    Back off for :attr:`retry_after` seconds (the sync/async clients can do this for you if
    retries are enabled). Per-merchant limits are configurable in the dashboard.

    See https://docs.altpay.money/docs/http-codes#rate-limit
    """

    default_hint = "Rate limited. Back off and retry after the Retry-After interval."

    def __init__(self, status_code: int, *, retry_after: float | None = None, **kwargs: object) -> None:
        self.retry_after = retry_after
        super().__init__(status_code, **kwargs)  # type: ignore[arg-type]


class ServerError(APIError):
    """HTTP 5xx, the API failed to handle a well-formed request.

    Includes ``503 security_backend_unavailable`` (the API's nonce/replay store is down) and
    ``502`` from an upstream payment provider. These are server-side and usually transient.
    Retry with backoff. If it persists, quote :attr:`APIError.request_id` to support.

    See https://docs.altpay.money/docs/http-codes#server
    """

    default_hint = "Server-side error. Retry with backoff; quote request_id if it persists."


# Backwards-friendly alias so callers can ``except altpay.Forbidden`` without the underscore.
Forbidden = PermissionError_


def error_from_status(
    status_code: int,
    *,
    detail: str | None = None,
    response_body: object = None,
    request_id: str | None = None,
    retry_after: float | None = None,
) -> APIError:
    """Map an HTTP status code to the most specific :class:`APIError` subclass.

    Used by the clients to turn a non-2xx response into a typed exception. The mapping is by
    status family; ``detail`` further refines the human hint via the built-in catalogue.
    """
    if status_code == 401:
        return AuthenticationError(status_code, detail=detail, response_body=response_body, request_id=request_id)
    if status_code == 403:
        return PermissionError_(status_code, detail=detail, response_body=response_body, request_id=request_id)
    if status_code == 404:
        return NotFoundError(status_code, detail=detail, response_body=response_body, request_id=request_id)
    if status_code in (400, 422):
        return ValidationError(status_code, detail=detail, response_body=response_body, request_id=request_id)
    if status_code == 409:
        return ConflictError(status_code, detail=detail, response_body=response_body, request_id=request_id)
    if status_code == 429:
        return RateLimitError(
            status_code,
            retry_after=retry_after,
            detail=detail,
            response_body=response_body,
            request_id=request_id,
        )
    if status_code >= 500:
        return ServerError(status_code, detail=detail, response_body=response_body, request_id=request_id)
    return APIError(status_code, detail=detail, response_body=response_body, request_id=request_id)


# Per-``detail`` hints layered on top of the per-status defaults. Keep these terse and
# actionable; the prose lives in the docstrings and the docs site.
_HINTS: dict[str, str] = {
    "invalid_signature": AuthenticationError.default_hint,
    "invalid_request": ValidationError.default_hint,
    "invoice_not_found": "No invoice matches this uuid/order_id for your merchant.",
    "ip_not_allowed": "Your server IP is not in the API key's allowlist. Add it in the dashboard.",
    "ip_blocked": "This IP is blocked. Contact support to lift the block.",
    "rate_limited": RateLimitError.default_hint,
    "security_backend_unavailable": "The API's replay-protection store is temporarily down. Retry shortly.",
    "no_accepted_methods": "The requested networks are not in this merchant's accepted methods.",
    "quote_token_invalid": "The price quote token is invalid or expired. Request a fresh quote.",
}
