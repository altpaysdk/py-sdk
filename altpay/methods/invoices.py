"""Invoice and static-wallet endpoints.

Covers the ``/api/v2/invoice/*`` surface: create and read invoices, page through them, fetch
the method catalogue and balance, and manage static deposit wallets.

API reference: https://docs.altpay.money/docs/invoices
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable

from ..enums import FiatCurrency, PaymentStatus
from ..models import AssetBalance, Balance, Invoice, InvoicePage, Service, Wallet, WalletDeposit
from .base import APICall, Resource, drop_none


class Invoices(Resource):
    """Invoice and static-wallet operations. Reached via ``client.invoices``.

    On the sync client every method returns its result directly; on the async client it
    returns an awaitable of the same result (``await client.invoices.create(...)``).
    """

    def create(
        self,
        *,
        uuid: str,
        amount: Decimal | str | int | float,
        fiat_currency: FiatCurrency | str,
        lifetime: int = 60,
        networks: Iterable[str] | None = None,
        except_networks: Iterable[str] | None = None,
        url_callback: str | None = None,
        url_success: str | None = None,
        url_return: str | None = None,
    ) -> Invoice:
        """Create an invoice and get a hosted checkout URL.

        Args:
            uuid: Your idempotency key / order reference (1-64 chars). Echoed back as the
                invoice ``uuid`` and in webhooks as ``merchant_reference``. Reusing a value
                does not deduplicate server-side, so keep it unique per order.
            amount: The amount to charge, greater than zero. Passed as a string to preserve
                precision - prefer a Decimal over a float.
            fiat_currency: The invoice currency (``RUB``, ``USD`` or ``EUR``).
            lifetime: Minutes until the invoice expires, 60-1440 (default 60).
            networks: If given, restrict the payer to exactly these methods/networks.
            except_networks: If given, hide these methods/networks from the payer.
            url_callback: Your webhook URL; AltPay POSTs a signed ``payment.updated`` event
                here when the invoice is paid. Verify it with :class:`altpay.WebhookVerifier`.
            url_success: Optional redirect after a successful payment.
            url_return: Optional redirect after the payer cancels.

        Returns:
            The created :class:`~altpay.models.Invoice` (status ``CREATED``).

        Raises:
            altpay.ValidationError: A field is missing or invalid (amount <= 0, lifetime out
                of range, malformed URL).
            altpay.Forbidden: Your merchant account is not approved yet.

        API reference: https://docs.altpay.money/docs/invoices#create
        """
        payload = drop_none(
            {
                "uuid": uuid,
                "amount": _amount_str(amount),
                "fiat_currency": _enum_value(fiat_currency),
                "lifetime": lifetime,
                "networks": list(networks) if networks is not None else None,
                "except_networks": list(except_networks) if except_networks is not None else None,
                "url_callback": url_callback,
                "url_success": url_success,
                "url_return": url_return,
            }
        )
        return self._invoke(APICall("/api/v2/invoice/create", payload, Invoice.model_validate))

    def get(self, *, order_id: str | None = None, uuid: str | None = None) -> Invoice:
        """Fetch a single invoice by AltPay ``order_id`` or by your ``uuid``.

        Supply at least one identifier. If both are given, ``order_id`` takes precedence.

        Args:
            order_id: AltPay's invoice id (the ``order_id`` returned at creation).
            uuid: The ``uuid`` you supplied at creation.

        Returns:
            The :class:`~altpay.models.Invoice`.

        Raises:
            ValueError: Neither identifier was supplied.
            altpay.NotFoundError: No invoice matches for your merchant.

        API reference: https://docs.altpay.money/docs/invoices#get
        """
        if not order_id and not uuid:
            raise ValueError("Pass order_id or uuid to identify the invoice.")
        payload = drop_none({"order_id": order_id, "uuid": uuid})
        return self._invoke(APICall("/api/v2/invoice/get", payload, Invoice.model_validate))

    def list(
        self,
        *,
        status: PaymentStatus | str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> InvoicePage:
        """List invoices, newest first, with cursor pagination.

        Args:
            status: Filter by status (e.g. ``PaymentStatus.PAYED``).
            date_from: ISO-8601 lower bound on creation time (inclusive).
            date_to: ISO-8601 upper bound on creation time.
            cursor: The ``next_cursor`` from a previous page; omit for the first page.
            limit: Page size, 1-200 (default 50).

        Returns:
            An :class:`~altpay.models.InvoicePage`. Page by feeding ``next_cursor`` back as
            ``cursor`` until ``has_more`` is ``False``.

        API reference: https://docs.altpay.money/docs/invoices#list
        """
        payload = drop_none(
            {
                "status": _enum_value(status) if status is not None else None,
                "date_from": date_from,
                "date_to": date_to,
                "cursor": cursor,
                "limit": limit,
            }
        )
        return self._invoke(APICall("/api/v2/invoice/list", payload, InvoicePage.model_validate))

    def services(self) -> list[Service]:
        """List the payment methods available to your merchant, with limits and fees.

        Returns:
            A list of :class:`~altpay.models.Service`.

        API reference: https://docs.altpay.money/docs/invoices#services
        """
        return self._invoke(
            APICall(
                "/api/v2/invoice/services",
                None,
                lambda result: [Service.model_validate(item) for item in result["items"]],
            )
        )

    def balance(self, *, fiat_currency: FiatCurrency | str = FiatCurrency.USD) -> Balance:
        """Get your balance valued in one fiat currency, broken down by asset.

        Args:
            fiat_currency: The currency to value the balance in (default ``USD``).

        Returns:
            A :class:`~altpay.models.Balance`.

        API reference: https://docs.altpay.money/docs/invoices#balance
        """
        payload = {"fiat_currency": _enum_value(fiat_currency)}
        return self._invoke(APICall("/api/v2/invoice/balance", payload, Balance.model_validate))

    def create_wallet(self, *, network: str, order_id: str) -> Wallet:
        """Create a static (persistent) deposit wallet for a network.

        Funds sent to the returned address are credited to your balance and attributed to
        ``order_id``. Unlike an invoice, a static wallet does not expire.

        Args:
            network: The network to create the wallet on (e.g. ``"TRX"``), 1-32 chars.
            order_id: Your reference for the wallet, 1-64 chars.

        Returns:
            The created :class:`~altpay.models.Wallet`.

        API reference: https://docs.altpay.money/docs/static-wallets#create
        """
        payload = {"network": network, "order_id": order_id}
        return self._invoke(
            APICall("/api/v2/invoice/wallet/create", payload, Wallet.model_validate)
        )

    def list_wallets(self, *, limit: int = 100, offset: int = 0) -> list[Wallet]:
        """List your static deposit wallets.

        Args:
            limit: Page size, 1-200 (default 100).
            offset: Number of wallets to skip (default 0).

        Returns:
            A list of :class:`~altpay.models.Wallet`.

        API reference: https://docs.altpay.money/docs/static-wallets#list
        """
        payload = {"limit": limit, "offset": offset}
        return self._invoke(
            APICall(
                "/api/v2/invoice/wallet/list",
                payload,
                lambda result: [Wallet.model_validate(item) for item in result["items"]],
            )
        )

    def wallet_deposits(self, *, wallet_uuid: str) -> list[WalletDeposit]:
        """List the deposits received at one static wallet.

        Args:
            wallet_uuid: The ``wallet_uuid`` from :meth:`create_wallet` / :meth:`list_wallets`.

        Returns:
            A list of :class:`~altpay.models.WalletDeposit`, newest first.

        API reference: https://docs.altpay.money/docs/static-wallets#deposits
        """
        payload = {"wallet_uuid": wallet_uuid}
        return self._invoke(
            APICall(
                "/api/v2/invoice/wallet/deposits",
                payload,
                lambda result: [WalletDeposit.model_validate(item) for item in result["items"]],
            )
        )

    def assets(self, *, fiat_currency: FiatCurrency | str = FiatCurrency.USD) -> AssetBalance:
        """Get your per-token balance valued in one fiat, with allocation percentages.

        Richer than :meth:`balance`: lists every supported asset (zero if unheld), each with
        a ``withdrawable`` flag and its share of the fiat total.

        Args:
            fiat_currency: The currency to value balances in (default ``USD``).

        Returns:
            An :class:`~altpay.models.AssetBalance`.

        API reference: https://docs.altpay.money/docs/invoices#assets
        """
        payload = {"fiat_currency": _enum_value(fiat_currency)}
        return self._invoke(APICall("/api/v2/invoice/assets", payload, AssetBalance.model_validate))


def _amount_str(amount: Decimal | str | int | float) -> str:
    """Render an amount as a plain decimal string (no scientific notation)."""
    if isinstance(amount, str):
        return amount
    return format(Decimal(str(amount)), "f")


def _enum_value(value: Any) -> str:
    """Return the wire value of a str-enum member, or the string unchanged."""
    return value.value if hasattr(value, "value") else str(value)
