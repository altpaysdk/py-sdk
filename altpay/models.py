"""Typed response models.

Every API response is wrapped by the server as ``{"result": {...}}``. The clients unwrap
``result`` and validate the inner object into one of the models below, so you work with typed
objects (with IDE completion and parsed types) rather than raw dicts.

Monetary and crypto amounts are returned by the API as strings to avoid float rounding, and
are kept as :class:`~decimal.Decimal` here for safe arithmetic. Timestamps are timezone-aware
:class:`~datetime.datetime`. Identifiers that the API types as UUID are kept as ``str`` for
ergonomics (you rarely need UUID semantics, and stringly ids round-trip cleanly).

These models are read-only views of API output. Request bodies are built from plain
arguments by the method modules, so there is no separate "request model" to construct.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from .enums import FiatCurrency, MerchantStatus, PaymentStatus, WithdrawalStatus


class _Model(BaseModel):
    """Shared base: ignore unknown fields so a server adding a field never breaks an old SDK."""

    model_config = ConfigDict(extra="ignore", frozen=True)


class Invoice(_Model):
    """An invoice (payment), as returned by create/get/list.

    Attributes:
        uuid: Your own idempotency key supplied at creation (``None`` if you did not set one).
        order_id: AltPay's identifier for the invoice (the ``external_id``). Use this for
            :meth:`~altpay.methods.invoices.Invoices.get` and to correlate webhooks.
        amount: The invoice amount in :attr:`fiat_currency`.
        fiat_currency: The currency the invoice is denominated in.
        payer_amount: The amount the payer must send in the selected crypto/asset, or ``None``
            until a method is selected.
        payer_currency: The asset the payer pays in (e.g. ``"USDT"``, ``"BTC"``), or ``None``.
        network: The settlement network of the selected method, or ``None``.
        address: The deposit address to pay to, or ``None`` until a method is selected or for
            off-chain methods.
        url: The hosted checkout URL to redirect the payer to.
        expired_at: Unix timestamp (seconds) when the invoice expires, or ``None``.
        status: The current :class:`~altpay.enums.PaymentStatus`.
        is_final: Whether ``status`` is terminal (no further changes).
        created_at: When the invoice was created.
        updated_at: When it last changed.
    """

    uuid: str | None = None
    order_id: str
    amount: Decimal
    fiat_currency: str
    payer_amount: Decimal | None = None
    payer_currency: str | None = None
    network: str | None = None
    address: str | None = None
    url: str
    expired_at: int | None = None
    status: PaymentStatus
    is_final: bool
    created_at: datetime
    updated_at: datetime


class InvoicePage(_Model):
    """One page of invoices from :meth:`~altpay.methods.invoices.Invoices.list`.

    Attributes:
        items: The invoices on this page (newest first).
        next_cursor: Pass this as ``cursor`` to fetch the next page, or ``None``.
        has_more: Whether another page exists. Equivalent to ``next_cursor is not None``
            when the page was full.
    """

    items: list[Invoice]
    next_cursor: str | None = None
    has_more: bool = False


class ServiceCommission(_Model):
    """The fee schedule for a payment method."""

    percent: Decimal
    fixed: Decimal
    fixed_currency: str


class Service(_Model):
    """A payment method available to your merchant, with its limits and fees.

    Attributes:
        method: The method identifier (matches :class:`~altpay.enums.PaymentMethod` values).
        network: Settlement network, or ``None`` for off-chain providers.
        currency: The asset the payer pays in, or ``None``.
        settlement_asset: The asset the payment settles to your balance in.
        min_amount: The minimum invoice amount accepted for this method.
        commission: The fee schedule.
    """

    method: str
    network: str | None = None
    currency: str | None = None
    settlement_asset: str
    min_amount: Decimal
    commission: ServiceCommission


class BalanceAsset(_Model):
    """One asset line in the per-asset balance breakdown.

    Attributes:
        asset: The asset ticker.
        amount: The held amount in that asset.
        fiat_value: The amount valued in the requested fiat currency.
        rate: The asset->fiat rate used.
        allocation_pct: This asset's share of the total balance, 0-100.
    """

    asset: str
    amount: Decimal
    fiat_value: Decimal
    rate: Decimal
    allocation_pct: float


class Balance(_Model):
    """The merchant's balance valued in one fiat currency.

    Attributes:
        fiat_currency: The currency every fiat value is expressed in.
        total_fiat: The total balance in that currency.
        balances: Per-asset breakdown.
    """

    fiat_currency: FiatCurrency
    total_fiat: Decimal
    balances: list[BalanceAsset]


class Wallet(_Model):
    """A static (persistent) deposit wallet.

    Attributes:
        wallet_uuid: AltPay's identifier for the wallet.
        address: The deposit address.
        network: The wallet's network, or ``None``.
        currency: The asset it accepts, or ``None``.
        merchant_reference: Your ``order_id`` for the wallet, or ``None``.
    """

    wallet_uuid: str
    address: str
    network: str | None = None
    currency: str | None = None
    merchant_reference: str | None = None


class Account(_Model):
    """Your merchant and API-key identity (from ``me.get``).

    Attributes:
        merchant_id: Your merchant UUID.
        merchant_name: Display name.
        merchant_status: Account status - only ``APPROVED`` can create invoices.
        api_key_id: UUID of the API key the request authenticated with.
        api_key_name: The key's label.
        api_key_active: Whether the key is active.
        api_key_created_at: When the key was issued.
    """

    merchant_id: str
    merchant_name: str
    merchant_status: MerchantStatus
    api_key_id: str
    api_key_name: str
    api_key_active: bool
    api_key_created_at: datetime


class MethodBalanceItem(_Model):
    """Paid volume for one method, in that method's settlement asset (from ``me.balance``).

    Attributes:
        currency: The settlement asset/currency of the method.
        network: The method's network.
        total_paid: Total paid volume in that asset.
        invoices_count: Number of paid invoices contributing to it.
    """

    currency: str
    network: str
    total_paid: Decimal
    invoices_count: int


class MethodBalance(_Model):
    """Per-method paid-volume breakdown (from ``me.balance``)."""

    merchant_id: str
    items: list[MethodBalanceItem]


class Statistics(_Model):
    """Aggregate payment statistics for your merchant (from ``me.statistics``).

    Attributes:
        total_invoices: Count of all invoices ever created.
        paid_invoices: Count that reached ``PAID``.
        expired_invoices: Count that expired.
        total_volume_usd: Total paid volume valued in USD.
        average_amount_usd: Average invoice amount in USD.
    """

    total_invoices: int
    paid_invoices: int
    expired_invoices: int
    total_volume_usd: Decimal
    average_amount_usd: Decimal


class AssetBalanceItem(_Model):
    """One asset line in the richer per-token balance (from ``invoices.assets``).

    Attributes:
        asset: The asset ticker.
        method: The payment method this asset settles through.
        amount: The held amount in that asset.
        fiat_equivalent: The amount valued in the requested fiat currency.
        rate: The asset->fiat rate used.
        allocation_pct: This asset's share of the total balance, 0-100.
        withdrawable: Whether this asset can be withdrawn (on-chain methods and RUB).
    """

    asset: str
    method: str
    amount: Decimal
    fiat_equivalent: Decimal
    rate: Decimal
    allocation_pct: float
    withdrawable: bool


class AssetBalance(_Model):
    """Per-token balance valued in one fiat, with allocation (from ``invoices.assets``).

    Attributes:
        fiat_currency: The currency every fiat value is expressed in.
        total_fiat: The total balance in that currency.
        items: Per-asset breakdown, largest holding first.
    """

    fiat_currency: FiatCurrency
    total_fiat: Decimal
    items: list[AssetBalanceItem]


class WalletDeposit(_Model):
    """A single credit received at a static deposit wallet (from ``invoices.wallet_deposits``).

    Attributes:
        id: AltPay's id for the deposit.
        asset: The asset received.
        method: The payment method/network it arrived on.
        gross_amount: The amount received before fees.
        fee_amount: The platform fee taken.
        net_amount: The amount credited to your balance (gross minus fee).
        balance_after: Your balance in that asset right after the credit.
        status: ``"credited"`` or ``"swept"``.
        tx_hash: The on-chain transaction hash, if known.
        created_at: When the deposit was credited.
    """

    id: str
    asset: str
    method: str
    gross_amount: Decimal
    fee_amount: Decimal
    net_amount: Decimal
    balance_after: Decimal
    status: str
    tx_hash: str | None = None
    created_at: datetime


class WithdrawalFee(_Model):
    """A fee preview for a withdrawal (from ``withdrawals.estimate_fee``).

    Attributes:
        asset: The asset the fees are expressed in.
        network: The network the estimate is for, or ``None``.
        fee_percent: The service percent fee that would be charged.
        network_fee_amount: The approximate network fee, in the asset's units. The operator
            sets the authoritative value at approval, so treat this as an estimate.
    """

    asset: str
    network: str | None = None
    fee_percent: Decimal
    network_fee_amount: Decimal


class Withdrawal(_Model):
    """A payout request (from ``withdrawals.create``/``list``).

    Attributes:
        id: AltPay's id for the request.
        asset: The asset being withdrawn.
        amount: The gross amount debited from your balance.
        fee_percent_amount: The service fee frozen at request time, or ``None``.
        network_fee_amount: The network fee, set at approval, or ``None`` while pending.
        net_amount: The amount actually paid out, finalized at approval, or ``None``.
        address: The destination address.
        network: The chosen settlement network, or ``None``.
        status: The current :class:`~altpay.enums.WithdrawalStatus`.
        created_at: When the request was made.
    """

    id: str
    asset: str
    amount: Decimal
    fee_percent_amount: Decimal | None = None
    network_fee_amount: Decimal | None = None
    net_amount: Decimal | None = None
    address: str | None = None
    network: str | None = None
    status: WithdrawalStatus
    created_at: datetime


class WebhookEvent(_Model):
    """The decoded body of a ``payment.updated`` webhook.

    Use :meth:`altpay.WebhookVerifier.parse` to verify-and-decode a raw request into this
    model. The amount fields are :class:`~decimal.Decimal`; ``status`` is a
    :class:`~altpay.enums.PaymentStatus`.

    Attributes:
        event: Always ``"payment.updated"`` for now.
        payment_id: AltPay's payment UUID.
        merchant_reference: Your ``uuid`` from invoice creation, if any.
        external_id: AltPay's ``order_id`` for the invoice.
        status: The new payment status (``PAID`` for a successful payment).
        invoice_amount: The invoice amount in :attr:`invoice_currency`.
        invoice_currency: The invoice currency.
        invoice_amount_usd: The invoice amount valued in USD.
        amount_due: The total amount the payer owed.
        amount_paid: The amount actually received.
        confirmation_count: On-chain confirmations observed.
        required_confirmations: Confirmations required to finalize.
    """

    event: str
    payment_id: str
    merchant_reference: str | None = None
    external_id: str
    status: PaymentStatus
    invoice_amount: Decimal | None = None
    invoice_currency: str | None = None
    invoice_amount_usd: Decimal | None = None
    amount_due: Decimal | None = None
    amount_paid: Decimal | None = None
    confirmation_count: int | None = None
    required_confirmations: int | None = None
