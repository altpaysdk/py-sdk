"""Enumerations used across the public API.

These mirror the server's vocabulary exactly. Each is a ``str`` enum, so a member compares
equal to its wire value (``PaymentStatus.PAID == "paid"``) and serializes transparently -
you can pass either a member or the raw string anywhere the SDK accepts one.
"""

from __future__ import annotations

from enum import Enum


class PaymentStatus(str, Enum):
    """Lifecycle state of an invoice.

    * ``WAITING`` - issued, awaiting payment.
    * ``PARTIAL`` - underpaid (received less than due); still open.
    * ``PAID`` - fully paid and confirmed (final). The webhook fires on this transition.
    * ``EXPIRED`` - the lifetime window elapsed before payment (final).
    * ``FAILED`` - the payment failed or was rejected (final).

    ``WAITING``/``PARTIAL`` are non-final; the other three are final
    (see :attr:`is_final`).

    The member values are the wire strings of the public REST API
    (``"waiting"``, ``"paid"``, ...). The webhook (``payment.updated``) reports the
    same lifecycle with the server's *internal* uppercase names (``"CREATED"``,
    ``"PAYED"``, ...); :meth:`_missing_` maps those onto the same members so both
    transports decode to one canonical value.
    """

    WAITING = "waiting"
    PARTIAL = "partial"
    PAID = "paid"
    EXPIRED = "expired"
    FAILED = "failed"

    @property
    def is_final(self) -> bool:
        """Whether no further status change is possible (PAID, EXPIRED or FAILED)."""
        return self in (PaymentStatus.PAID, PaymentStatus.EXPIRED, PaymentStatus.FAILED)


class PaymentMethod(str, Enum):
    """A payment method the payer can settle with.

    On-chain methods deliver to a generated deposit address; ``LOLZTEAM`` and ``CRYPTOBOT``
    are off-chain providers that redirect the payer to a hosted page. ``USDT_*`` names encode
    the network the stablecoin settles on (e.g. ``USDT_TRC20`` is USDT on TRON).
    """

    TRX = "TRX"
    BTC = "BTC"
    ETH = "ETH"
    LTC = "LTC"
    BNB = "BNB"
    TON = "TON"
    SOLANA = "SOLANA"
    USDT_TRC20 = "USDT_TRC20"
    USDT_ETH = "USDT_ETH"
    USDT_BSC = "USDT_BSC"
    USDT_TON = "USDT_TON"
    USDT_SOLANA = "USDT_SOLANA"
    LOLZTEAM = "LOLZTEAM"
    CRYPTOBOT = "CRYPTOBOT"


class FiatCurrency(str, Enum):
    """A fiat currency an invoice can be denominated in."""

    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"


class FeePaidBy(str, Enum):
    """Who bears the platform commission on an invoice.

    * ``MERCHANT`` (default) - the commission is deducted from your settlement; the payer is
      charged only the invoice amount.
    * ``CUSTOMER`` - the commission is added on top of what the payer is charged, so you are
      settled the full invoice principal.
    """

    MERCHANT = "MERCHANT"
    CUSTOMER = "CUSTOMER"


class MerchantStatus(str, Enum):
    """Account status of a merchant.

    Only ``APPROVED`` merchants can create invoices; the others block payment creation
    (``PENDING_REVIEW`` until onboarding completes, ``SUSPENDED``/``ARCHIVED``/``REJECTED``
    permanently or until support intervenes).
    """

    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"
    SUSPENDED = "SUSPENDED"


class WithdrawalStatus(str, Enum):
    """Lifecycle state of a payout request.

    A new request is ``PENDING`` review; an operator then ``APPROVED`` it (funds are paid
    out) or ``REJECTED`` it (the reserved amount is credited back to your balance).
    """

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
