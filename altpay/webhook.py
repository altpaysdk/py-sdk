"""Webhook verification.

AltPay POSTs a signed ``payment.updated`` event to your ``url_callback`` when an invoice is
paid. Always verify the signature before trusting the body. An unverified webhook is just
an unauthenticated HTTP request and must never drive order fulfilment.

:class:`WebhookVerifier` binds your webhook secret once and exposes two calls: :meth:`verify`
(boolean check) and :meth:`parse` (verify-then-decode into a typed
:class:`~altpay.models.WebhookEvent`). Pass the RAW request body bytes. Re-serializing the
parsed JSON changes the bytes and breaks the hash.

Verification checks the signature, the body hash and the timestamp freshness window, but it
does NOT deduplicate. Two valid deliveries of the same event (AltPay's own retries, or a
replay inside the freshness window) both verify. Fulfilment must be idempotent on your side.
Key it on ``event.payment_id`` (or your ``merchant_reference``) so a repeat is a no-op.

See https://docs.altpay.money/docs/webhooks
"""

from __future__ import annotations

from .errors import AuthenticationError
from .models import WebhookEvent
from .signing import verify_webhook


class WebhookVerifier:
    """Verifies and decodes incoming AltPay webhooks for one secret.

    Args:
        secret: Your webhook secret (the ``webhook_secret`` issued with the API key).
        target: The request-target the webhook is signed over: the path your endpoint is
            mounted at, including any query string, exactly as configured in ``url_callback``
            (e.g. ``"/altpay/webhook"``). The signature covers this, so it must match.
        tolerance_seconds: Reject events whose timestamp is older than this (replay window);
            default 300s, set 0 to disable.
    """

    __slots__ = ("_secret", "_target", "_tolerance")

    def __init__(self, secret: str, *, target: str, tolerance_seconds: int = 300) -> None:
        if not secret:
            raise ValueError("A webhook secret is required. See https://docs.altpay.money/docs/webhooks")
        self._secret = secret
        self._target = target
        self._tolerance = tolerance_seconds

    def verify(self, body: bytes, headers: dict[str, str]) -> bool:
        """Return whether ``body``/``headers`` are a valid, fresh, correctly-signed webhook.

        Args:
            body: The RAW request body bytes (not the parsed JSON re-serialized).
            headers: The incoming request headers (case-insensitive lookup is fine).

        Returns:
            ``True`` if the signature, body hash and timestamp all check out.
        """
        return verify_webhook(
            secret=self._secret,
            body=body,
            headers=headers,
            target=self._target,
            tolerance_seconds=self._tolerance,
        )

    def parse(self, body: bytes, headers: dict[str, str]) -> WebhookEvent:
        """Verify the webhook and decode it into a typed :class:`~altpay.models.WebhookEvent`.

        Args:
            body: The RAW request body bytes.
            headers: The incoming request headers.

        Returns:
            The decoded :class:`~altpay.models.WebhookEvent`.

        Raises:
            altpay.AuthenticationError: The signature is invalid, the body was tampered with,
                or the event is a stale replay. Respond ``401`` and ignore the body.

        Example (any framework, here the essentials)::

            verifier = WebhookVerifier(secret, target="/altpay/webhook")
            event = verifier.parse(raw_body, request.headers)
            if event.status == "paid":
                fulfil(event.merchant_reference)
        """
        if not self.verify(body, headers):
            raise AuthenticationError(
                401,
                detail="invalid_webhook_signature",
                hint="Webhook signature/body/timestamp check failed. Reject with 401.",
            )
        return WebhookEvent.model_validate_json(body)
