"""Merchant credentials.

An immutable holder for the four secrets the SDK needs. Grouping them keeps the client
constructors clean and makes it obvious which value plays which role. A frequent source of
``invalid_signature`` errors is swapping the public ``api_key`` with the secret ``api_secret``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Credentials:
    """The credentials issued for one API key in your dashboard.

    Args:
        merchant_id: Your merchant UUID. Sent in the clear as ``X-Merchant-Id``.
        api_key: The public key identifier (``vc_live_...``). Sent in the clear as
            ``X-Api-Key``; the server looks it up by hash.
        api_secret: The signing secret. Never transmitted, it is the HMAC key for every
            request signature. Keep it server-side only.
        webhook_secret: The secret used to sign webhooks AltPay sends you. Optional here;
            required only if you verify webhooks with this SDK. Distinct from ``api_secret``.

    All four are shown once at key creation and cannot be retrieved later, so store them in
    your secret manager. See https://docs.altpay.money/docs/authentication
    """

    merchant_id: str
    api_key: str
    api_secret: str
    webhook_secret: str | None = None

    def __post_init__(self) -> None:
        if not self.merchant_id or not self.api_key or not self.api_secret:
            raise ValueError(
                "merchant_id, api_key and api_secret are all required. "
                "See https://docs.altpay.money/docs/authentication"
            )
