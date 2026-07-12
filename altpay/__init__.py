"""AltPay - the official Python SDK for the AltPay crypto-payments API.

Quick start (sync)::

    from decimal import Decimal
    from altpay import AltPay, Credentials

    client = AltPay(Credentials(
        merchant_id="YOUR_MERCHANT_ID",
        api_key="vc_live_...",
        api_secret="YOUR_API_SECRET",
    ))
    invoice = client.invoices.create(
        uuid="order-42",
        amount=Decimal("100.00"),
        fiat_currency="USD",
        url_callback="https://example.com/altpay/webhook",
    )
    print(invoice.url)

Quick start (async)::

    from altpay import AsyncAltPay, Credentials

    async with AsyncAltPay(creds) as client:
        invoice = await client.invoices.create(uuid="order-42", amount="100.00", fiat_currency="USD")

Verifying a webhook::

    from altpay import WebhookVerifier
    verifier = WebhookVerifier(webhook_secret, target="/altpay/webhook")
    event = verifier.parse(raw_body, request_headers)  # raises on a bad signature

Documentation: https://docs.altpay.money/docs
"""

from .__meta__ import __version__
from .client import AltPay, AsyncAltPay
from .credentials import Credentials
from .enums import FeePaidBy, FiatCurrency, MerchantStatus, PaymentMethod, PaymentStatus, WithdrawalStatus
from .errors import (
    AltPayError,
    AltPayTransportError,
    APIError,
    AuthenticationError,
    ConflictError,
    Forbidden,
    NotFoundError,
    PermissionError_,
    RateLimitError,
    ServerError,
    ValidationError,
)
from .models import (
    Account,
    AssetBalance,
    AssetBalanceItem,
    Balance,
    BalanceAsset,
    Invoice,
    InvoicePage,
    MethodBalance,
    MethodBalanceItem,
    Service,
    ServiceCommission,
    Statistics,
    Wallet,
    WalletDeposit,
    WebhookEvent,
    Withdrawal,
    WithdrawalFee,
)
from .webhook import WebhookVerifier

__all__ = [
    "__version__",
    # Clients
    "AltPay",
    "AsyncAltPay",
    "Credentials",
    # Webhooks
    "WebhookVerifier",
    # Enums
    "PaymentStatus",
    "PaymentMethod",
    "FiatCurrency",
    "FeePaidBy",
    "MerchantStatus",
    "WithdrawalStatus",
    # Models
    "Invoice",
    "InvoicePage",
    "Service",
    "ServiceCommission",
    "Balance",
    "BalanceAsset",
    "AssetBalance",
    "AssetBalanceItem",
    "Wallet",
    "WalletDeposit",
    "Account",
    "MethodBalance",
    "MethodBalanceItem",
    "Statistics",
    "Withdrawal",
    "WithdrawalFee",
    "WebhookEvent",
    # Errors
    "AltPayError",
    "AltPayTransportError",
    "APIError",
    "AuthenticationError",
    "Forbidden",
    "PermissionError_",
    "NotFoundError",
    "ValidationError",
    "ConflictError",
    "RateLimitError",
    "ServerError",
]
